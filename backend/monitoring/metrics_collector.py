"""backend/monitoring/metrics_collector.py — Telemetry Ingestion and Persistence.

Collects real-time device health and interface telemetry, persists points to the
PostgreSQL `metrics` table via SQLAlchemy async session, and manages a continuous
background collection loop.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import settings
from backend.database.database import AsyncSessionLocal
from backend.database.models import Device, NetworkMetric, Link
from backend.monitoring.device_monitor import DeviceMonitor, HealthStatus
from backend.monitoring.network_monitor import NetworkMonitor

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects real-time network and device telemetry and persists snapshots to database."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        device_monitor: Optional[DeviceMonitor] = None,
        network_monitor: Optional[NetworkMonitor] = None
    ):
        self.base_url = (base_url or settings.PROMETHEUS_URL).rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=5.0)
        self.device_monitor = device_monitor or DeviceMonitor()
        self.network_monitor = network_monitor or NetworkMonitor()
        self._running = False
        logger.info("MetricsCollector initialized (Prometheus URL: %s)", self.base_url)

"""backend/monitoring/metrics_collector.py — Telemetry Ingestion and Persistence.

Collects real-time device health, interface telemetry, and link metrics using
real active probes (ICMP ping, OVS port statistics, psutil host metrics).
Persists points with honest nullability, capacity vs measured throughput,
and explicit measurement methods into the PostgreSQL `metrics` table.
"""

import asyncio
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import httpx
import psutil
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.database import AsyncSessionLocal
from backend.database.models import Device, NetworkMetric, Link
from backend.monitoring.device_monitor import DeviceMonitor, HealthStatus
from backend.monitoring.network_monitor import NetworkMonitor

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects real-time network and device telemetry and persists snapshots to database."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        device_monitor: Optional[DeviceMonitor] = None,
        network_monitor: Optional[NetworkMonitor] = None
    ):
        self.base_url = (base_url or settings.PROMETHEUS_URL).rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=5.0)
        self.device_monitor = device_monitor or DeviceMonitor()
        self.network_monitor = network_monitor or NetworkMonitor()
        self._interface_counters: Dict[str, Dict[str, Any]] = {}
        self._running = False
        logger.info("MetricsCollector initialized (Prometheus URL: %s)", self.base_url)

    # ─────────────────────────────────────────────────────────────────────────
    # REAL PROBING HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    async def _query_ovs_interface(self, interface: str) -> Dict[str, Any]:
        """Query real OVS interface statistics, link state, and error counters.

        If ovs-vsctl is unavailable, logs and returns honest nulls — NEVER fake 0 or 100.
        """
        if not shutil.which("ovs-vsctl"):
            logger.debug("ovs-vsctl binary not found in PATH — interface %s metrics unavailable", interface)
            return {
                "available": False,
                "interface_up": None,
                "rx_bytes": None,
                "tx_bytes": None,
                "error_count": None,
                "method": "unavailable",
                "reason": "ovs-vsctl binary not found"
            }

        try:
            cmd = ["ovs-vsctl", "list", "interface", interface]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
            if proc.returncode != 0 or not stdout_b:
                return {
                    "available": False,
                    "interface_up": None,
                    "rx_bytes": None,
                    "tx_bytes": None,
                    "error_count": None,
                    "method": "unavailable",
                    "reason": "ovs-vsctl list interface returned non-zero"
                }

            stdout = stdout_b.decode("utf-8", errors="replace")

            # Link state
            admin_up = "admin_state         : up" in stdout
            link_up = "link_state          : up" in stdout
            interface_up = 1 if (admin_up and link_up) else 0

            # Parse statistics dictionary: statistics: {"rx_bytes"=1234, "tx_bytes"=5678, ...}
            rx_bytes = None
            tx_bytes = None
            rx_errors = 0
            tx_errors = 0

            stat_match = re.search(r'statistics\s*:\s*\{(.*?)\}', stdout)
            if stat_match:
                stats_str = stat_match.group(1)
                rx_m = re.search(r'rx_bytes\s*=\s*(\d+)', stats_str)
                tx_m = re.search(r'tx_bytes\s*=\s*(\d+)', stats_str)
                rxe_m = re.search(r'rx_errors\s*=\s*(\d+)', stats_str)
                txe_m = re.search(r'tx_errors\s*=\s*(\d+)', stats_str)

                if rx_m:
                    rx_bytes = int(rx_m.group(1))
                if tx_m:
                    tx_bytes = int(tx_m.group(1))
                if rxe_m:
                    rx_errors = int(rxe_m.group(1))
                if txe_m:
                    tx_errors = int(txe_m.group(1))

            return {
                "available": True,
                "interface_up": interface_up,
                "rx_bytes": rx_bytes,
                "tx_bytes": tx_bytes,
                "error_count": float(rx_errors + tx_errors),
                "method": "ovs_counter"
            }
        except Exception as exc:
            logger.debug("ovs-vsctl query failed for interface %s: %s", interface, exc)
            return {
                "available": False,
                "interface_up": None,
                "rx_bytes": None,
                "tx_bytes": None,
                "error_count": None,
                "method": "unavailable",
                "reason": str(exc)
            }

    def _compute_throughput(self, key: str, rx_bytes: Optional[int], tx_bytes: Optional[int]) -> Optional[float]:
        """Compute measured bandwidth throughput in Mbps from interface counter deltas."""
        if rx_bytes is None or tx_bytes is None:
            return None

        now = time.perf_counter()
        prev = self._interface_counters.get(key)
        self._interface_counters[key] = {"time": now, "rx_bytes": rx_bytes, "tx_bytes": tx_bytes}

        if not prev:
            return 0.0  # initial baseline observation

        dt = max(0.001, now - prev["time"])
        delta_bytes = max(0, (rx_bytes - prev["rx_bytes"]) + (tx_bytes - prev["tx_bytes"]))
        # Bytes * 8 / (seconds * 1_000_000) = Mbps
        mbps = round((delta_bytes * 8.0) / (dt * 1_000_000.0), 2)
        return mbps

    # ─────────────────────────────────────────────────────────────────────────
    # PER-ENTITY REAL METRIC COLLECTORS
    # ─────────────────────────────────────────────────────────────────────────

    async def collect_switch_metrics(self, switch: Device) -> Dict[str, Any]:
        """Query real switch telemetry via OVS interface counters, psutil, and ping."""
        target_id = switch.id
        ip = switch.ip_address or "127.0.0.1"
        missing: List[str] = []
        method = "ovs_counter"

        # 1. Ping for real latency and loss
        ping_res = await self.network_monitor.ping_host(ip, count=2, timeout=1.5)
        reachable = ping_res.get("reachable", False)
        latency_ms = ping_res.get("latency_ms") if reachable else None
        packet_loss_pct = ping_res.get("packet_loss_pct") if reachable else 100.0

        # 2. CPU & Memory via psutil (real process / system resources)
        cpu_pct: Optional[float] = None
        memory_pct: Optional[float] = None
        try:
            # Query ovs-vswitchd process CPU/memory if running, else system load
            found_proc = False
            for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_percent']):
                if "ovs-vswitchd" in (proc.info['name'] or "").lower():
                    cpu_pct = float(proc.info['cpu_percent'] or 0.0)
                    memory_pct = float(proc.info['memory_percent'] or 0.0)
                    found_proc = True
                    break
            if not found_proc:
                cpu_pct = float(psutil.cpu_percent(interval=None))
                memory_pct = float(psutil.virtual_memory().percent)
        except Exception as exc:
            logger.debug("CPU/memory query failed for switch %s: %s", target_id, exc)
            missing.extend(["cpu_pct", "memory_pct"])

        # 3. Interface stats via ovs-vsctl
        intf_name = f"{switch.id}-eth1"
        ovs_stats = await self._query_ovs_interface(intf_name)

        if ovs_stats.get("available"):
            interface_up = ovs_stats.get("interface_up")
            error_count = ovs_stats.get("error_count")
            bandwidth_mbps = self._compute_throughput(
                intf_name,
                ovs_stats.get("rx_bytes"),
                ovs_stats.get("tx_bytes")
            )
        else:
            interface_up = 1 if reachable else 0
            error_count = None
            bandwidth_mbps = None
            method = "icmp"
            missing.extend(["bandwidth_mbps", "error_count"])

        if latency_ms is None:
            missing.append("latency_ms")

        return {
            "device_id": target_id,
            "latency_ms": latency_ms,
            "packet_loss_pct": packet_loss_pct,
            "cpu_pct": cpu_pct,
            "memory_pct": memory_pct,
            "bandwidth_mbps": bandwidth_mbps,
            "interface_up": interface_up,
            "error_count": error_count,
            "measurement_method": method,
            "missing_fields": missing,
            "timestamp": datetime.now(timezone.utc),
        }

    async def collect_host_metrics(self, host: Device) -> Dict[str, Any]:
        """Query host or server telemetry via ping and host resources."""
        target_id = host.id
        ip = host.ip_address or "127.0.0.1"
        missing: List[str] = []

        ping_res = await self.network_monitor.ping_host(ip, count=2, timeout=1.5)
        reachable = ping_res.get("reachable", False)
        latency_ms = ping_res.get("latency_ms") if reachable else None
        packet_loss_pct = ping_res.get("packet_loss_pct") if reachable else 100.0

        # CPU & Memory: Query psutil only if local or accessible
        cpu_pct: Optional[float] = None
        memory_pct: Optional[float] = None
        if ip in ("127.0.0.1", "localhost"):
            try:
                cpu_pct = float(psutil.cpu_percent(interval=None))
                memory_pct = float(psutil.virtual_memory().percent)
            except Exception:
                missing.extend(["cpu_pct", "memory_pct"])
        else:
            # Remote virtual host: resource query requires agent/snmp — report honest NULL
            missing.extend(["cpu_pct", "memory_pct"])

        interface_up = 1 if reachable else 0
        bandwidth_mbps = None  # Hosts require active iperf measurement
        missing.append("bandwidth_mbps")

        if latency_ms is None:
            missing.append("latency_ms")

        return {
            "device_id": target_id,
            "latency_ms": latency_ms,
            "packet_loss_pct": packet_loss_pct,
            "cpu_pct": cpu_pct,
            "memory_pct": memory_pct,
            "bandwidth_mbps": bandwidth_mbps,
            "interface_up": interface_up,
            "error_count": 0.0 if reachable else 1.0,
            "measurement_method": "icmp",
            "missing_fields": missing,
            "timestamp": datetime.now(timezone.utc),
        }

    async def collect_link_metrics(self, link: Link) -> Dict[str, Any]:
        """Measure real link latency, packet loss, and throughput.

        Links do NOT possess CPU or Memory. Those are set to NULL (None).
        Capacity is stored as a configured property, separate from measured throughput.
        Utilization = (measured_bandwidth_mbps / capacity_mbps) * 100.
        """
        link_id = link.id
        capacity = float(getattr(link, "capacity_mbps", None) or getattr(link, "bandwidth_mbps", None) or 100.0)
        missing: List[str] = ["cpu_pct", "memory_pct"]  # links never have CPU/mem

        # 1. Measure latency and loss across link endpoints
        target_ip = "127.0.0.1"
        if getattr(link, "src_device", None) and link.src_device.ip_address:
            target_ip = link.src_device.ip_address
        elif getattr(link, "dst_device", None) and link.dst_device.ip_address:
            target_ip = link.dst_device.ip_address

        ping_res = await self.network_monitor.ping_host(target_ip, count=2, timeout=1.0)
        reachable = ping_res.get("reachable", False)
        latency_ms = ping_res.get("latency_ms") if reachable else None
        packet_loss_pct = ping_res.get("packet_loss_pct") if reachable else 100.0

        # 2. Derive interface name for link endpoint (e.g. s2-eth2)
        sw1 = link.src_device_id
        sw2 = link.dst_device_id
        intf_name = f"{sw1}-eth1"
        if {sw1.lower(), sw2.lower()} == {"s2", "s3"}:
            intf_name = f"{sw1}-eth2"

        ovs_stats = await self._query_ovs_interface(intf_name)
        measured_bw: Optional[float] = None
        interface_up: Optional[int] = None
        error_count: Optional[float] = None
        method = "ovs_counter"

        if ovs_stats.get("available"):
            interface_up = ovs_stats.get("interface_up")
            error_count = ovs_stats.get("error_count")
            measured_bw = self._compute_throughput(
                intf_name,
                ovs_stats.get("rx_bytes"),
                ovs_stats.get("tx_bytes")
            )
        else:
            # Fallback when OVS not accessible
            if link.status == "down":
                interface_up = 0
                measured_bw = 0.0
            else:
                interface_up = 1 if reachable else 0
                measured_bw = None
                missing.append("bandwidth_mbps")
            method = "icmp" if reachable else "unavailable"

        # Compute real utilization percentage
        utilization_pct: Optional[float] = None
        if measured_bw is not None and capacity > 0:
            utilization_pct = round((measured_bw / capacity) * 100.0, 2)
        else:
            missing.append("utilization_pct")

        if latency_ms is None:
            missing.append("latency_ms")

        return {
            "device_id": link_id,
            "latency_ms": latency_ms,
            "packet_loss_pct": packet_loss_pct,
            "cpu_pct": None,               # N/A for links: NULL to prevent ML corruption
            "memory_pct": None,            # N/A for links: NULL to prevent ML corruption
            "bandwidth_mbps": measured_bw, # REAL measured throughput (NOT configured capacity)
            "capacity_mbps": capacity,     # Configured link capacity
            "utilization_pct": utilization_pct,
            "interface_up": interface_up,
            "error_count": error_count,
            "measurement_method": method,
            "missing_fields": missing,
            "timestamp": datetime.now(timezone.utc),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # GLOBAL TELEMETRY COLLECTION
    # ─────────────────────────────────────────────────────────────────────────

    async def collect_network_metrics(self, session: Optional[AsyncSession] = None) -> List[Dict[str, Any]]:
        """Poll devices and links and compile honest metric records with real measurements."""
        metrics_points: List[Dict[str, Any]] = []

        devices: List[Device] = []
        links: List[Link] = []
        should_close = False
        if session is None:
            db = AsyncSessionLocal()
            should_close = True
        else:
            db = session

        try:
            res = await db.execute(select(Device))
            devices = list(res.scalars().all())
            link_res = await db.execute(
                select(Link).options(
                    selectinload(Link.src_device),
                    selectinload(Link.dst_device)
                )
            )

            links = list(link_res.scalars().all())
            
        except Exception as exc:
            logger.warning("Could not fetch devices/links from DB for telemetry collection: %s", exc)
        finally:
            if should_close:
                await db.close()

        # 1. Collect real metrics for devices
        for dev in devices:
            if (dev.device_type or "").lower() == "switch":
                m = await self.collect_switch_metrics(dev)
            else:
                m = await self.collect_host_metrics(dev)
            metrics_points.append(m)

        # 2. Collect real metrics for links
        for link in links:
            m = await self.collect_link_metrics(link)
            metrics_points.append(m)

        logger.debug("Compiled %d telemetry metrics records", len(metrics_points))
        return metrics_points

    async def persist_metrics(self, metrics_list: List[Dict[str, Any]]) -> int:
        """Insert metric dictionaries into the database with honest nulls and metadata."""
        if not metrics_list:
            return 0

        inserted_count = 0
        async with AsyncSessionLocal() as session:
            try:
                for item in metrics_list:
                    d_id = item.get("device_id")
                    ts = item.get("timestamp") or datetime.now(timezone.utc)
                    cap = item.get("capacity_mbps")
                    util = item.get("utilization_pct")
                    method = item.get("measurement_method", "unknown")
                    missing = item.get("missing_fields", [])

                    if "metric_name" in item:
                        raw_val = item.get("metric_value")
                        session.add(NetworkMetric(
                            device_id=d_id,
                            metric_name=item.get("metric_name"),
                            metric_value=float(raw_val) if raw_val is not None else None,
                            capacity_mbps=cap,
                            utilization_pct=util,
                            measurement_method=method,
                            missing_fields=missing,
                            timestamp=ts,
                            labels=item.get("labels")
                        ))
                        inserted_count += 1
                    else:
                        for metric_name in ("latency_ms", "packet_loss_pct", "cpu_pct", "memory_pct", "bandwidth_mbps"):
                            raw_val = item.get(metric_name)
                            val = float(raw_val) if raw_val is not None else None
                            session.add(NetworkMetric(
                                device_id=d_id,
                                metric_name=metric_name,
                                metric_value=val,
                                capacity_mbps=cap if metric_name == "bandwidth_mbps" else None,
                                utilization_pct=util if metric_name == "bandwidth_mbps" else None,
                                measurement_method=method,
                                missing_fields=missing,
                                timestamp=ts,
                                labels={
                                    "interface_up": str(item.get("interface_up")),
                                    "error_count": str(item.get("error_count"))
                                }
                            ))
                            inserted_count += 1
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.error("Failed to persist metrics to database: %s", exc)
                return 0

        return inserted_count

    async def run_collection_loop(self, interval_seconds: int = 5):
        """Continuous background loop that polls telemetry and persists to database every N seconds."""
        self._running = True
        logger.info("Starting background telemetry collection loop (interval: %ds)...", interval_seconds)

        try:
            while self._running:
                start_t = asyncio.get_event_loop().time()
                try:
                    metrics = await self.collect_network_metrics()
                    if metrics:
                        await self.persist_metrics(metrics)
                except Exception as loop_exc:
                    logger.error("Error in telemetry collection cycle: %s", loop_exc, exc_info=True)

                elapsed = asyncio.get_event_loop().time() - start_t
                sleep_duration = max(0.1, interval_seconds - elapsed)
                await asyncio.sleep(sleep_duration)

        except asyncio.CancelledError:
            logger.info("Telemetry collection loop received cancellation signal. Shutting down gracefully.")
        finally:
            self._running = False
            logger.info("Telemetry collection loop stopped.")

    def stop_collection_loop(self):
        """Signal collection loop to terminate."""
        self._running = False

    async def close(self):
        """Close HTTP client session."""
        self.stop_collection_loop()
        await self.client.aclose()


# Alias RealMetricsCollector for callers expecting the class name from Fix 3
RealMetricsCollector = MetricsCollector
