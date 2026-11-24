"""backend/api/deps.py — FastAPI Dependency Injection Helpers.

Provides database session retrieval, current aggregated metrics from the DB,
and active incidents retrieval with real database queries.
"""

import logging
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from backend.database.database import get_db
from backend.database.models import Device, Link, Incident, NetworkMetric

logger = logging.getLogger(__name__)


async def get_current_metrics(
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Query and compute live aggregated metrics from actual DB records.

    If database has no metric/device records, returns zeroed data with
    `data_unavailable: True` flag — NEVER fakes healthy values.
    """
    # 1. Check devices count and status
    dev_query = select(
        Device.status,
        func.count(Device.id)
    ).group_by(Device.status)
    dev_res = await db.execute(dev_query)
    device_status_counts = dict(dev_res.all())
    total_devices = sum(device_status_counts.values())

    # 2. Check active incidents
    inc_query = select(func.count(Incident.id)).where(
        Incident.status.in_(["detected", "diagnosing", "mitigating"])
    )
    inc_res = await db.execute(inc_query)
    active_incidents = inc_res.scalar() or 0

    # 3. Query the latest metrics per device/metric_name
    # Get recent metrics (e.g. latency, packet_loss, cpu)
    metric_subq = (
        select(
            NetworkMetric.device_id,
            NetworkMetric.metric_name,
            NetworkMetric.metric_value,
            func.row_number().over(
                partition_by=(NetworkMetric.device_id, NetworkMetric.metric_name),
                order_by=desc(NetworkMetric.timestamp)
            ).label("rn")
        ).subquery()
    )

    latest_metrics_q = select(
        metric_subq.c.metric_name,
        func.avg(metric_subq.c.metric_value).label("avg_val")
    ).where(metric_subq.c.rn == 1).group_by(metric_subq.c.metric_name)

    metrics_res = await db.execute(latest_metrics_q)
    metric_averages = {row.metric_name: float(row.avg_val) for row in metrics_res.all()}

    # If there are no devices and no metrics recorded at all
    if total_devices == 0 and not metric_averages:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "data_unavailable": True,
            "network_health_score": 0.0,
            "total_devices": 0,
            "devices_up": 0,
            "devices_down": 0,
            "devices_degraded": 0,
            "active_incidents": 0,
            "average_latency_ms": 0.0,
            "packet_loss_rate": 0.0,
            "message": "Telemetry database is empty. No live monitoring data available."
        }

    # Extract averages or fallback to 0.0
    avg_latency = metric_averages.get("latency_ms", metric_averages.get("latency", 0.0))
    avg_loss = metric_averages.get("packet_loss_pct", metric_averages.get("packet_loss", 0.0))

    devices_down = device_status_counts.get("down", 0)
    devices_degraded = device_status_counts.get("degraded", 0)
    devices_up = device_status_counts.get("active", 0) + device_status_counts.get("up", 0)

    # Compute network health score: 100 - weighted penalties
    # Penalties:
    # Each down device: -25 pts (or proportional if many devices)
    # Each degraded device: -10 pts
    # High latency penalty: max 20 pts if > 100ms
    # Packet loss penalty: max 30 pts if > 10%
    penalty = 0.0
    if total_devices > 0:
        penalty += (devices_down / total_devices) * 50.0
        penalty += (devices_degraded / total_devices) * 20.0
    
    if avg_latency > 20.0:
        penalty += min(20.0, ((avg_latency - 20.0) / 100.0) * 20.0)
    if avg_loss > 0.0:
        penalty += min(30.0, (avg_loss / 5.0) * 30.0)
    
    if active_incidents > 0:
        penalty += min(20.0, active_incidents * 5.0)

    health_score = max(0.0, min(100.0, round(100.0 - penalty, 2)))

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "data_unavailable": False,
        "network_health_score": health_score,
        "total_devices": total_devices,
        "devices_up": devices_up,
        "devices_down": devices_down,
        "devices_degraded": devices_degraded,
        "active_incidents": active_incidents,
        "average_latency_ms": round(avg_latency, 2),
        "packet_loss_rate": round(avg_loss, 4),
    }


async def get_active_incidents(
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = None,
    severity_filter: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[Incident]:
    """Query active or historical incidents with filtering and pagination from DB."""
    query = select(Incident)

    if status_filter:
        query = query.where(Incident.status == status_filter)
    if severity_filter:
        query = query.where(Incident.severity == severity_filter)
    if device_id:
        query = query.where(Incident.affected_device_id == device_id)

    query = query.order_by(desc(Incident.detected_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())
