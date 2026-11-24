"""FastAPI Main Application Entry Point.

Initializes FastAPI app, middleware (CORS, Request logging),
lifespan startup/shutdown handlers with database & Prometheus health checks,
and registers API routers.
"""

import os
import json
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, status
from fastapi.middleware.cors import CORSMiddleware
import httpx
from sqlalchemy import select, func, or_, text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.config import settings
from backend.database.database import init_db, AsyncSessionLocal
from backend.database.models import Device, NetworkMetric, Link, Incident
from backend.api.routes import router as api_router
from backend.api.auth import router as auth_router, limiter, validate_ws_token
from backend.ws.manager import manager, WebSocketEvents
from backend.services import incident_service, recovery_policy_service, recovery_queue
from backend.detection.fault_detection import FaultDetector
from backend.monitoring.metrics_collector import MetricsCollector
from backend.monitoring.network_monitor import NetworkMonitor
from backend.monitoring.device_monitor import DeviceMonitor

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sentinelnet.main")


async def run_startup_checks():
    """Verify database population and Prometheus observability reachability on startup."""
    logger.info("Executing SentinelNet pre-flight environment checks...")

    # 1. Database Check
    try:
        async with AsyncSessionLocal() as session:
            dev_count = (await session.execute(select(func.count(Device.id)))).scalar() or 0
            metric_count = (await session.execute(select(func.count(NetworkMetric.id)))).scalar() or 0

            if dev_count == 0 or metric_count == 0:
                logger.warning(
                    "⚠️  [DATABASE WARNING] Telemetry database has %d devices and %d metric entries! "
                    "The dashboard endpoints will report 'data_unavailable: true' until network telemetry "
                    "is populated. (Run network_simulation/topology.py and traffic_generator.py to seed)",
                    dev_count, metric_count
                )
            else:
                logger.info(
                    "✓ Database verified: %d registered devices and %d recorded metric snapshots.",
                    dev_count, metric_count
                )
    except Exception as exc:
        logger.warning(
            "⚠️  [DATABASE CONNECTION WARNING] Could not query database on startup: %s. "
            "Ensure PostgreSQL is running at %s",
            exc, settings.DATABASE_URL
        )

    # 2. Prometheus Check
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.PROMETHEUS_URL}/-/healthy")
            if resp.status_code == 200:
                logger.info("✓ Prometheus server reachable at %s", settings.PROMETHEUS_URL)
            else:
                logger.warning(
                    "⚠️  [PROMETHEUS WARNING] Prometheus server at %s returned HTTP %d. "
                    "Live scrapers may experience telemetry delays.",
                    settings.PROMETHEUS_URL, resp.status_code
                )
    except Exception as exc:
        logger.warning(
            "⚠️  [PROMETHEUS WARNING] Prometheus server unreachable at %s (%s). "
            "Real-time external PromQL queries will be disabled or fall back to local database.",
            settings.PROMETHEUS_URL, exc
        )

    # 3. Ryu SDN Controller Check
    from backend.controller.sdn_controller import RyuSDNControllerClient
    try:
        sdn_client = RyuSDNControllerClient(base_url=settings.RYU_BASE_URL)
        alive = await sdn_client.is_controller_alive()
        await sdn_client.close()
    except Exception as exc:
        logger.warning("Ryu controller startup probe error: %s", exc)


# State tracking for continuous monitoring loop observability
monitoring_state = {
    "alive": False,
    "last_run_at": None,
    "last_error": None
}

metrics_collector = MetricsCollector()
fault_detector = FaultDetector()
ws_manager = manager
policy_service = recovery_policy_service


async def _process_detected_faults(target_id: str, faults: list, metrics: dict):
    """Persist incidents, broadcast WebSocket events, and enqueue for recovery."""
    try:
        async with AsyncSessionLocal() as session:
            # Check for existing active incident to avoid duplicate flooding
            stmt = select(Incident).where(
                or_(
                    Incident.affected_device_id == target_id,
                    Incident.affected_link_id == target_id
                )
            ).where(Incident.status.in_(["detected", "diagnosing"]))
            existing = (await session.execute(stmt)).scalars().first()
            if existing:
                return  # don't duplicate

            for fault in faults:
                incident = await incident_service.create_from_fault(target_id, fault, metrics, session=session)
                if incident:
                    logger.info("[Incident Created] ID: %s | Target: %s", incident.id, target_id)
                    await ws_manager.broadcast("INCIDENT_CREATED", incident.dict())
                    if await policy_service.should_auto_recover(incident, session=session):
                        await recovery_queue.enqueue(incident.id)
                        logger.info(f"Incident {incident.id} enqueued for auto-recovery")
    except Exception as e:
        logger.error("Failed to process detected faults for %s: %s", target_id, e)


async def monitoring_loop():
    """Continuous background loop collecting network metrics and detecting faults."""
    monitoring_state["alive"] = True
    while True:
        try:
            monitoring_state["last_run_at"] = datetime.now(timezone.utc).isoformat()
            metrics_list = await metrics_collector.collect_network_metrics()
            for metrics in metrics_list:
                target_id = metrics["device_id"]
                score = 0.0

                # Honest ML guard: skip inference when required features are NULL (e.g. links or unavailable OVS)
                ml_features = ["latency_ms", "packet_loss_pct", "cpu_pct", "memory_pct", "bandwidth_mbps", "interface_up", "error_count"]
                missing_ml = [f for f in ml_features if metrics.get(f) is None]

                if missing_ml:
                    logger.info("ML inference skipped: missing features %s for %s", missing_ml, target_id)
                elif fault_detector.anomaly_detector:
                    try:
                        pred = fault_detector.anomaly_detector.predict(metrics)
                        score = float(pred.get("anomaly_score", 0.0))
                    except Exception:
                        pass

                logger.info(
                    f"[Metric Collected] Target: {target_id} | Score: {score:.4f} | "
                    f"Method: {metrics.get('measurement_method', 'unknown')} | "
                    f"Measured BW: {metrics.get('bandwidth_mbps')} Mbps | "
                    f"Capacity: {metrics.get('capacity_mbps')} Mbps | "
                    f"Util: {metrics.get('utilization_pct')}%"
                )

                faults = fault_detector.detect(target_id, metrics)
                for fault in faults:
                    logger.warning(
                        f"[Fault Detected] Target: {target_id} | Type: {fault.fault_type} | Confidence: {fault.confidence:.2f}"
                    )
                    async with AsyncSessionLocal() as session:
                        stmt = select(Incident).where(
                            or_(
                                Incident.affected_device_id == target_id,
                                Incident.affected_link_id == target_id
                            )
                        ).where(Incident.status.in_(["detected", "diagnosing"]))
                        existing = (await session.execute(stmt)).scalars().first()
                        if existing:
                            continue  # don't duplicate

                        incident = await incident_service.create_from_fault(
                            target_id, fault, metrics, session=session
                        )
                        if incident:
                            logger.info(f"[Incident Created] ID: {incident.id} | Target: {target_id}")
                            await ws_manager.broadcast("INCIDENT_CREATED", incident.dict())
                            if await policy_service.should_auto_recover(incident, session=session):
                                await recovery_queue.enqueue(incident.id)
                                logger.info(f"Incident {incident.id} enqueued for auto-recovery")

            # Also persist latest telemetry snapshots to database for dashboard consumption
            try:
                await metrics_collector.persist_metrics(metrics_list)
            except Exception as persist_err:
                logger.debug("Telemetry persistence error: %s", persist_err)

            monitoring_state["last_error"] = None
        except asyncio.CancelledError:
            logger.info("Continuous telemetry monitoring loop stopped.")
            monitoring_state["alive"] = False
            break
        except Exception as e:
            logger.exception(f"Monitoring loop error (will retry in 5s): {e}")
            monitoring_state["last_error"] = str(e)
            await asyncio.sleep(5)
            continue

        await asyncio.sleep(getattr(settings, "MONITORING_INTERVAL_SECONDS", 5))


# Backward compatibility alias
metrics_collection_loop = monitoring_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for startup and shutdown event management."""
    logger.info("Initializing %s v%s...", settings.PROJECT_NAME, settings.VERSION)

    # 1. Test DB connection (init tables + execute SELECT 1) — CRASH if DB fails
    try:
        await init_db()
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_type = "Postgres" if "postgres" in settings.DATABASE_URL.lower() else "SQLite"
        logger.info(f"✓ Database: connected ({db_type})")
    except Exception as db_err:
        logger.critical(f"FATAL: Database connection failed on startup: {db_err}")
        raise RuntimeError(f"Database connection failed: {db_err}") from db_err

    # 2. Test ML model loaded — CRASH if ML model fails to load
    try:
        det = FaultDetector()
        if not det.anomaly_detector or not getattr(det.anomaly_detector, "model", None):
            raise RuntimeError("IsolationForest model artifact failed to load")
        v = det.anomaly_detector.model_version
        n = len(det.anomaly_detector.feature_cols)
        logger.info(f"✓ ML model: loaded (version {v}, features {n})")
    except Exception as ml_err:
        logger.critical(f"FATAL: ML model failed to load on startup: {ml_err}")
        raise RuntimeError(f"ML model failed to load: {ml_err}") from ml_err

    # 3. Test Ryu connection (call is_controller_alive()) — DO NOT crash if Ryu unreachable
    from backend.controller.sdn_controller import RyuSDNControllerClient
    sdn_client = RyuSDNControllerClient(base_url=settings.RYU_BASE_URL)
    try:
        alive = await sdn_client.is_controller_alive()
        if alive:
            switches = await sdn_client.get_switches()
            logger.info(f"✓ Ryu: reachable at {sdn_client.base_url} ({len(switches)} switches)")
        else:
            logger.warning(f"⚠ Ryu: unreachable at {sdn_client.base_url} — automated recovery disabled")
    except Exception as ryu_err:
        logger.warning(f"⚠ Ryu: unreachable at {sdn_client.base_url} ({ryu_err}) — automated recovery disabled")
    finally:
        await sdn_client.close()

    # 4. Test Mininet — DO NOT crash if absent
    from backend.simulation.failure_service import FailureInjectionService
    from network_simulation.failure_injector import FailureInjector
    mn_alive = False
    try:
        dummy_svc = FailureInjectionService(db=None, failure_injector=FailureInjector())
        mn_alive = await dummy_svc._mininet_alive()
    except Exception:
        mn_alive = False

    if mn_alive:
        logger.info("✓ Mininet: running (active topology)")
    else:
        logger.warning("⚠ Mininet: not detected — failure injection will return 503")

    # Run existing pre-flight environment checks (Prometheus telemetry checks, etc.)
    await run_startup_checks()

    # Start background recovery queue worker
    recovery_queue.start()

    # Start continuous real-telemetry monitoring loop
    monitoring_task = asyncio.create_task(monitoring_loop(), name="monitoring_loop")

    logger.info("SentinelNet backend services started successfully.")
    yield
    logger.info("Shutting down SentinelNet backend services...")
    monitoring_task.cancel()
    monitoring_state["alive"] = False
    try:
        await monitoring_task
    except asyncio.CancelledError:
        pass
    await recovery_queue.stop()
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend microservices for AI-Powered Self-Healing SDN Network.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware configuration
# Replaced allow_origins=["*"] with explicit origins to support allow_credentials=True
allowed_origins_list = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiter setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Register API v1 routes
app.include_router(auth_router, prefix="/api")
app.include_router(api_router, prefix="/api")


@app.get("/api/health/deep", tags=["Health"])
async def get_deep_health():
    """Deep component health check reporting live statuses across all system layers."""
    # 1. Database
    db_status = "ok"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"

    # 2. Ryu SDN Controller
    from backend.controller.sdn_controller import RyuSDNControllerClient
    sdn = RyuSDNControllerClient(base_url=settings.RYU_BASE_URL)
    ryu_reachable = False
    switch_count = 0
    try:
        ryu_reachable = await sdn.is_controller_alive()
        if ryu_reachable:
            switches = await sdn.get_switches()
            switch_count = len(switches)
    except Exception:
        pass
    finally:
        await sdn.close()

    # 3. Mininet Emulation Substrate
    from backend.simulation.failure_service import FailureInjectionService
    from network_simulation.failure_injector import FailureInjector
    mn_running = False
    try:
        dummy_svc = FailureInjectionService(db=None, failure_injector=FailureInjector())
        mn_running = await dummy_svc._mininet_alive()
    except Exception:
        mn_running = False

    # 4. ML Model Artifacts
    ml_loaded = False
    ml_version = "unknown"
    ml_features = []
    try:
        det = FaultDetector()
        if det.anomaly_detector and getattr(det.anomaly_detector, "model", None):
            ml_loaded = True
            ml_version = det.anomaly_detector.model_version
            ml_features = list(det.anomaly_detector.feature_cols)
    except Exception:
        pass

    # 5. Recovery Queue
    q_size = recovery_queue.qsize if isinstance(recovery_queue.qsize, int) else recovery_queue.qsize()
    worker_alive = bool(
        getattr(recovery_queue, "_running", False)
        and getattr(recovery_queue, "_worker_task", None)
        and not recovery_queue._worker_task.done()
    )

    # 6. Monitoring Loop
    loop_alive = bool(monitoring_state.get("alive", False))
    last_run = monitoring_state.get("last_run_at")
    last_err = monitoring_state.get("last_error")

    return {
        "database": db_status,
        "ryu": {
            "reachable": ryu_reachable,
            "url": settings.RYU_BASE_URL,
            "switch_count": switch_count
        },
        "mininet": {
            "running": mn_running,
            "topology": "UniversityTopology (3 switches, 5 hosts, 1 controller)" if mn_running else "none"
        },
        "ml_model": {
            "loaded": ml_loaded,
            "version": ml_version,
            "features": ml_features
        },
        "recovery_queue": {
            "size": q_size,
            "worker_alive": worker_alive
        },
        "monitoring_loop": {
            "alive": loop_alive,
            "last_run_at": last_run,
            "last_error": last_err
        }
    }


# WebSocket Endpoint with JWT Authentication
@app.websocket("/ws/live")
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """Real-time bidirectional WebSocket stream for telemetry, anomalies, and remediation events.
    
    Authenticates via query parameter '?token=...' or via initial frame:
    {"type": "AUTH", "token": "Bearer <JWT>"}
    Rejects unauthorized connections with WebSocket closure code 1008 (Policy Violation).
    """
    user = None
    async with AsyncSessionLocal() as session:
        if token:
            user = await validate_ws_token(token, session)
            if not user:
                logger.warning("WebSocket connection rejected: Invalid or expired query token.")
                await websocket.close(code=1008)  # Policy Violation
                return

        if not user:
            # Accept temporarily to receive the initial AUTH frame from the client
            await websocket.accept()
            try:
                first_msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                msg_data = json.loads(first_msg_raw)
                raw_token = msg_data.get("token") or msg_data.get("access_token")
                if (msg_data.get("type") == "AUTH" or "token" in msg_data) and raw_token:
                    user = await validate_ws_token(raw_token, session)
                if not user:
                    logger.warning("WebSocket connection rejected: Initial AUTH frame invalid.")
                    await websocket.close(code=1008)
                    return
                await manager.register_accepted(websocket, user)
            except Exception as exc:
                logger.warning("WebSocket connection rejected: Timed out waiting for AUTH frame (%s)", exc)
                try:
                    await websocket.close(code=1008)
                except Exception:
                    pass
                return
        else:
            await manager.connect(websocket, user)

    try:
        while True:
            text = await websocket.receive_text()
            if text.strip() == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health probe."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting local development server on %s:%d", settings.HOST, settings.PORT)
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=True)
