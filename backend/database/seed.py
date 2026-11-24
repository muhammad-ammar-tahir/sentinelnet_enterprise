"""backend/database/seed.py — Idempotent Realistic Database Seeding Script.

Populates SentinelNet database with real entities matching Mininet UniversityTopology:
- 1 SDN controller (c0)
- 3 OpenFlow switches (s1, s2, s3) with real DPIDs (1, 2, 3)
- 4 Student Lab hosts (h1-h4) with real IPs
- 1 Server (srv1) with 10.0.0.50
- 7 links matching Mininet physical ports (including failable s2-s3 link)
- 3 historical incidents (one resolved, one rolled back, one failed)
- 1 default self-healing recovery policy
- 1 demo operator user with bcrypt/pbkdf2 hashed password
- 60 minutes of synthetic historical telemetry points (5-min intervals)

Safe to run repeatedly (Idempotent: merges existing records).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from sqlalchemy import select, delete

from backend.database.database import AsyncSessionLocal, init_db
from backend.database.models import Device, Link, Incident, RecoveryAction, Policy, User, NetworkMetric, AuditLog

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinelnet.seed")


def hash_password(password: str) -> str:
    """Generate bcrypt hash for user credentials.

    Raises RuntimeError if bcrypt is unavailable — never falls back to a weak
    hash algorithm.  Install ``passlib[bcrypt]`` (included in requirements.txt).
    """
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.hash(password)
    except Exception as exc:
        raise RuntimeError(
            "bcrypt hashing failed — cannot seed users with weak password hashes. "
            "Ensure 'passlib[bcrypt]' and 'bcrypt' are installed "
            "(pip install passlib[bcrypt] bcrypt). "
            f"Original error: {exc}"
        ) from exc


async def seed_database() -> Dict[str, int]:
    """Execute idempotent database population."""
    logger.info("Starting SentinelNet database seeding procedure...")
    await init_db()

    counts = {
        "devices": 0,
        "links": 0,
        "incidents": 0,
        "recovery_actions": 0,
        "policies": 0,
        "users": 0,
        "metrics": 0,
        "audit_logs": 0
    }

    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        # ---------------------------------------------------------------------
        # 1. Devices (1 Controller, 3 Switches, 4 Hosts, 1 Server)
        # ---------------------------------------------------------------------
        devices_data = [
            # SDN Controller
            {
                "id": "c0",
                "name": "Ryu OpenFlow Controller",
                "device_type": "controller",
                "ip_address": "127.0.0.1",
                "mac_address": None,
                "dpid": None,
                "status": "active",
                "location": "Central NOC / Cloud"
            },
            # Core Switch s1
            {
                "id": "s1",
                "name": "Core Switch S1",
                "device_type": "switch",
                "ip_address": "10.0.0.1",
                "mac_address": "00:00:00:00:00:01",
                "dpid": "1",
                "status": "active",
                "location": "Campus Core Backbone"
            },
            # Distribution Switch s2 (Left - Student Lab A)
            {
                "id": "s2",
                "name": "Distribution Switch S2 (Lab A)",
                "device_type": "switch",
                "ip_address": "10.0.0.2",
                "mac_address": "00:00:00:00:00:02",
                "dpid": "2",
                "status": "active",
                "location": "Engineering Hall - Lab A"
            },
            # Distribution Switch s3 (Right - Server Room & Lab B)
            {
                "id": "s3",
                "name": "Distribution Switch S3 (Server Room)",
                "device_type": "switch",
                "ip_address": "10.0.0.3",
                "mac_address": "00:00:00:00:00:03",
                "dpid": "3",
                "status": "active",
                "location": "Data Center - Rack 4"
            },
            # Hosts h1, h2 (under s2)
            {
                "id": "h1",
                "name": "Student Workstation H1",
                "device_type": "host",
                "ip_address": "10.0.1.1",
                "mac_address": "00:00:00:00:01:01",
                "dpid": None,
                "status": "active",
                "location": "Lab A - Desk 1"
            },
            {
                "id": "h2",
                "name": "Student Workstation H2",
                "device_type": "host",
                "ip_address": "10.0.1.2",
                "mac_address": "00:00:00:00:01:02",
                "dpid": None,
                "status": "active",
                "location": "Lab A - Desk 2"
            },
            # Hosts h3, h4 (under s3)
            {
                "id": "h3",
                "name": "Research Terminal H3",
                "device_type": "host",
                "ip_address": "10.0.1.3",
                "mac_address": "00:00:00:00:01:03",
                "dpid": None,
                "status": "active",
                "location": "Lab B - Desk 1"
            },
            {
                "id": "h4",
                "name": "Research Terminal H4",
                "device_type": "host",
                "ip_address": "10.0.1.4",
                "mac_address": "00:00:00:00:01:04",
                "dpid": None,
                "status": "active",
                "location": "Lab B - Desk 2"
            },
            # Server srv1 (under s3)
            {
                "id": "srv1",
                "name": "Academic LMS & File Server",
                "device_type": "server",
                "ip_address": "10.0.0.50",
                "mac_address": "00:00:00:00:00:50",
                "dpid": None,
                "status": "active",
                "location": "Data Center - Server Pod 1"
            }
        ]

        for d_info in devices_data:
            existing = (await session.execute(select(Device).where(Device.id == d_info["id"]))).scalar_one_or_none()
            if existing:
                for k, v in d_info.items():
                    setattr(existing, k, v)
                existing.updated_at = now
            else:
                session.add(Device(**d_info, created_at=now, updated_at=now))
            counts["devices"] += 1

        await session.flush()

        # ---------------------------------------------------------------------
        # 2. Links (Matching UniversityTopology physical ports)
        # ---------------------------------------------------------------------
        links_data = [
            # Trunk s1 <-> s2 (port 1 on s1, port 1 on s2)
            {
                "id": "link-s1-s2",
                "src_device_id": "s1",
                "dst_device_id": "s2",
                "src_port": 1,
                "dst_port": 1,
                "link_type": "primary",
                "status": "up",
                "bandwidth_mbps": 100.0,
                "latency_ms": 1.0,
                "packet_loss_rate": 0.0,
                "current_utilization": 14.5
            },
            # Trunk s1 <-> s3 (port 2 on s1, port 1 on s3)
            {
                "id": "link-s1-s3",
                "src_device_id": "s1",
                "dst_device_id": "s3",
                "src_port": 2,
                "dst_port": 1,
                "link_type": "primary",
                "status": "up",
                "bandwidth_mbps": 100.0,
                "latency_ms": 1.0,
                "packet_loss_rate": 0.0,
                "current_utilization": 8.2
            },
            # Cross-Trunk s2 <-> s3 (FAILEABLE LINK: port 2 on s2, port 2 on s3)
            {
                "id": "link-s2-s3",
                "src_device_id": "s2",
                "dst_device_id": "s3",
                "src_port": 2,
                "dst_port": 2,
                "link_type": "primary",
                "status": "up",
                "bandwidth_mbps": 100.0,
                "latency_ms": 2.0,
                "packet_loss_rate": 0.0,
                "current_utilization": 18.0
            },
            # Access Links: Hosts to Switch s2
            {
                "id": "link-h1-s2",
                "src_device_id": "h1",
                "dst_device_id": "s2",
                "src_port": 0,
                "dst_port": 3,
                "link_type": "access",
                "status": "up",
                "bandwidth_mbps": 100.0,
                "latency_ms": 1.0,
                "packet_loss_rate": 0.0,
                "current_utilization": 2.5
            },
            {
                "id": "link-h2-s2",
                "src_device_id": "h2",
                "dst_device_id": "s2",
                "src_port": 0,
                "dst_port": 4,
                "link_type": "access",
                "status": "up",
                "bandwidth_mbps": 100.0,
                "latency_ms": 1.0,
                "packet_loss_rate": 0.0,
                "current_utilization": 1.8
            },
            # Access Links: Hosts to Switch s3
            {
                "id": "link-h3-s3",
                "src_device_id": "h3",
                "dst_device_id": "s3",
                "src_port": 0,
                "dst_port": 3,
                "link_type": "access",
                "status": "up",
                "bandwidth_mbps": 100.0,
                "latency_ms": 1.0,
                "packet_loss_rate": 0.0,
                "current_utilization": 3.1
            },
            # Access Link: Server srv1 to Switch s3 (port 5, 1Gbps)
            {
                "id": "link-srv1-s3",
                "src_device_id": "srv1",
                "dst_device_id": "s3",
                "src_port": 0,
                "dst_port": 5,
                "link_type": "access",
                "status": "up",
                "bandwidth_mbps": 1000.0,
                "latency_ms": 0.5,
                "packet_loss_rate": 0.0,
                "current_utilization": 12.0
            }
        ]

        for l_info in links_data:
            existing_l = (await session.execute(select(Link).where(Link.id == l_info["id"]))).scalar_one_or_none()
            if existing_l:
                for k, v in l_info.items():
                    setattr(existing_l, k, v)
            else:
                session.add(Link(**l_info))
            counts["links"] += 1

        await session.flush()

        # ---------------------------------------------------------------------
        # 3. Historical Incidents (1 Resolved, 1 Rolled Back, 1 Failed)
        # ---------------------------------------------------------------------
        incidents_data = [
            {
                "id": "inc-2024-001",
                "title": "Cross-trunk failure on s2-s3 segment",
                "severity": "critical",
                "status": "resolved",
                "affected_link_id": "link-s2-s3",
                "affected_device_id": "s2",
                "root_cause": "Fiber optic transceiver failure on Switch S2 port 2",
                "confidence_score": 0.96,
                "detected_at": now - timedelta(hours=3),
                "resolved_at": now - timedelta(hours=2, minutes=59, seconds=45),
                "metadata_payload": {"recovery_sla_ms": 850, "recovery_path": ["s2", "s1", "s3"]}
            },
            {
                "id": "inc-2024-002",
                "title": "Control-plane congestion during heavy exam traffic",
                "severity": "warning",
                "status": "rolled_back",
                "affected_link_id": "link-s1-s2",
                "affected_device_id": "s1",
                "root_cause": "Buffer overflow caused by unscheduled campus file transfer",
                "confidence_score": 0.84,
                "detected_at": now - timedelta(hours=1, minutes=30),
                "resolved_at": now - timedelta(hours=1, minutes=28),
                "metadata_payload": {"rollback_reason": "Verification latency exceeded 100ms constraint"}
            },
            {
                "id": "inc-2024-003",
                "title": "Unresponsive access port on Lab B terminal H4",
                "severity": "minor",
                "status": "failed",
                "affected_link_id": None,
                "affected_device_id": "h4",
                "root_cause": "Host network interface disconnected / power down",
                "confidence_score": 0.91,
                "detected_at": now - timedelta(minutes=45),
                "resolved_at": None,
                "metadata_payload": {"error": "no_alternate_path_available: single-homed access link"}
            }
        ]

        for inc_info in incidents_data:
            existing_inc = (await session.execute(select(Incident).where(Incident.id == inc_info["id"]))).scalar_one_or_none()
            if existing_inc:
                for k, v in inc_info.items():
                    setattr(existing_inc, k, v)
            else:
                session.add(Incident(**inc_info))
            counts["incidents"] += 1

        await session.flush()

        # ---------------------------------------------------------------------
        # 4. Recovery Actions
        # ---------------------------------------------------------------------
        actions_data = [
            {
                "id": "act-001",
                "incident_id": "inc-2024-001",
                "action_type": "flow_reroute",
                "status": "success",
                "target_dpid": "2",
                "parameters": {"path": ["h1", "s2", "s1", "s3", "srv1"], "new_out_port": 1},
                "execution_duration_ms": 42.5,
                "rollback_status": "none",
                "created_at": now - timedelta(hours=2, minutes=59, seconds=55),
                "executed_at": now - timedelta(hours=2, minutes=59, seconds=45)
            },
            {
                "id": "act-002",
                "incident_id": "inc-2024-002",
                "action_type": "flow_reroute",
                "status": "rolled_back",
                "target_dpid": "1",
                "parameters": {"path": ["s1", "s3"]},
                "execution_duration_ms": 38.0,
                "rollback_status": "reverted",
                "created_at": now - timedelta(hours=1, minutes=29),
                "executed_at": now - timedelta(hours=1, minutes=28)
            }
        ]

        for a_info in actions_data:
            existing_act = (await session.execute(select(RecoveryAction).where(RecoveryAction.id == a_info["id"]))).scalar_one_or_none()
            if existing_act:
                for k, v in a_info.items():
                    setattr(existing_act, k, v)
            else:
                session.add(RecoveryAction(**a_info))
            counts["recovery_actions"] += 1

        await session.flush()

        # ---------------------------------------------------------------------
        # 5. Policies
        # ---------------------------------------------------------------------
        policy_data = {
            "id": "pol-001",
            "name": "Default Campus Trunk Auto-Failover Policy",
            "rule_condition": "packet_loss_pct > 5.0 OR latency_ms > 100.0",
            "action_template": "reroute_via_backup_dijkstra",
            "is_active": True,
            "priority": 100
        }
        existing_pol = (await session.execute(select(Policy).where(Policy.id == policy_data["id"]))).scalar_one_or_none()
        if existing_pol:
            for k, v in policy_data.items():
                setattr(existing_pol, k, v)
        else:
            session.add(Policy(**policy_data))
        counts["policies"] += 1

        # ---------------------------------------------------------------------
        # 6. Seed Users (admin, operator, viewer with bcrypt hashed passwords)
        # ---------------------------------------------------------------------
        users_data = [
            {
                "id": "usr-admin-01",
                "username": "admin",
                "email": "admin@sentinelnet.edu",
                "hashed_password": hash_password("sentinelpass"),
                "role": "admin",
                "is_active": True,
                "created_at": now
            },
            {
                "id": "usr-operator-01",
                "username": "operator",
                "email": "operator@sentinelnet.edu",
                "hashed_password": hash_password("sentinelpass"),
                "role": "operator",
                "is_active": True,
                "created_at": now
            },
            {
                "id": "usr-viewer-01",
                "username": "viewer",
                "email": "viewer@sentinelnet.edu",
                "hashed_password": hash_password("sentinelpass"),
                "role": "viewer",
                "is_active": True,
                "created_at": now
            }
        ]
        for u in users_data:
            existing_usr = (await session.execute(
                select(User).where((User.id == u["id"]) | (User.username == u["username"]))
            )).scalar_one_or_none()
            if existing_usr:
                for k, v in u.items():
                    setattr(existing_usr, k, v)
            else:
                session.add(User(**u))
            counts["users"] += 1

        # ---------------------------------------------------------------------
        # 7. Audit Log
        # ---------------------------------------------------------------------
        audit_data = {
            "id": "audit-001",
            "action": "SYSTEM_DATABASE_SEEDED",
            "actor": "system_bootstrap",
            "details": {"source": "backend.database.seed", "devices_seeded": len(devices_data)},
            "created_at": now
        }
        existing_audit = (await session.execute(select(AuditLog).where(AuditLog.id == audit_data["id"]))).scalar_one_or_none()
        if not existing_audit:
            session.add(AuditLog(**audit_data))
            counts["audit_logs"] += 1

        # ---------------------------------------------------------------------
        # 8. 60 Minutes of Synthetic Historical Metrics (every 5 minutes)
        # ---------------------------------------------------------------------
        monitored_devices = ["s1", "s2", "s3", "srv1"]

        # Clean existing seed metrics for idempotency
        await session.execute(
            delete(NetworkMetric).where(
                NetworkMetric.device_id.in_(monitored_devices),
                NetworkMetric.timestamp >= now - timedelta(hours=2)
            )
        )

        metrics_to_insert = []

        for step in range(12):  # 12 * 5min = 60 minutes
            t_point = now - timedelta(minutes=(60 - step * 5))
            for dev_id in monitored_devices:
                # Base nominal latency and loss
                lat = 2.1 if dev_id != "s3" else 3.5
                loss = 0.0
                cpu = 24.0 + (step % 4) * 3.5
                mem = 48.0 + (step % 3) * 1.5

                metrics_to_insert.append(NetworkMetric(
                    device_id=dev_id,
                    metric_name="latency_ms",
                    metric_value=lat,
                    timestamp=t_point,
                    labels={"source": "seed_script", "interval": "5m"}
                ))
                metrics_to_insert.append(NetworkMetric(
                    device_id=dev_id,
                    metric_name="packet_loss_pct",
                    metric_value=loss,
                    timestamp=t_point,
                    labels={"source": "seed_script", "interval": "5m"}
                ))
                metrics_to_insert.append(NetworkMetric(
                    device_id=dev_id,
                    metric_name="cpu_pct",
                    metric_value=cpu,
                    timestamp=t_point,
                    labels={"source": "seed_script", "interval": "5m"}
                ))
                metrics_to_insert.append(NetworkMetric(
                    device_id=dev_id,
                    metric_name="memory_pct",
                    metric_value=mem,
                    timestamp=t_point,
                    labels={"source": "seed_script", "interval": "5m"}
                ))

        session.add_all(metrics_to_insert)
        counts["metrics"] = len(metrics_to_insert)

        await session.commit()

    logger.info("=================================================================")
    logger.info("   SentinelNet Database Seeding Completed Successfully")
    logger.info("=================================================================")
    for table_name, count in counts.items():
        logger.info("   ✓ %-18s : %d records inserted/synchronized", table_name, count)
    logger.info("=================================================================")
    return counts


if __name__ == "__main__":
    asyncio.run(seed_database())
