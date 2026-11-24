"""backend/api/schemas.py — Pydantic Request & Response Schemas for SentinelNet API.

Defines validated data transfer schemas for anomaly detection, incident management,
telemetry snapshots, and operational recovery actions.
"""

import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator


class DetectRequest(BaseModel):
    """Telemetry vector submitted for fault and anomaly detection.
    
    Contains all 7 features expected by the trained Isolation Forest and
    heuristic fault classification rules. No fabricated defaults for core metrics.
    Missing core features trigger HTTP 422 Unprocessable Entity.
    """
    target_id: str = Field(..., description="Device (e.g. 's1') or Link identifier (e.g. 'link-s2-s3')")
    latency_ms: float = Field(..., ge=0.0, description="Round-trip time in milliseconds")
    packet_loss_pct: float = Field(..., ge=0.0, le=100.0, description="Packet loss percentage [0.0 - 100.0]")
    cpu_pct: float = Field(..., ge=0.0, le=100.0, description="CPU utilization percentage [0.0 - 100.0]")
    memory_pct: float = Field(..., ge=0.0, le=100.0, description="Memory utilization percentage [0.0 - 100.0]")
    bandwidth_mbps: float = Field(..., ge=0.0, description="Bandwidth throughput or rate in Megabits per second (Mbps)")
    interface_up: bool = Field(..., description="True if link/interface carrier is operational, False if down")
    error_count: float = Field(default=0.0, ge=0.0, description="Interface RX/TX error or drop count")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "target_id": "s2",
                "latency_ms": 25.4,
                "packet_loss_pct": 0.0,
                "cpu_pct": 45.2,
                "memory_pct": 52.0,
                "bandwidth_mbps": 48.5,
                "interface_up": True,
                "error_count": 0.0
            }
        }
    )


class IncidentResponse(BaseModel):
    """Detailed representation of a recorded network incident."""
    id: str
    title: str
    severity: str
    status: str
    fault_type: Optional[str] = "link_failure"
    affected_entity: Optional[str] = None
    affected_device_id: Optional[str] = None
    affected_link_id: Optional[str] = None
    root_cause: Optional[str] = None
    confidence: float
    detected_at: str
    resolved_at: Optional[str] = None
    recovery_action_id: Optional[str] = None
    detection_time_ms: Optional[float] = 680.0
    metadata_payload: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True)


class MetricSnapshotResponse(BaseModel):
    """Aggregated global telemetry and health score."""
    timestamp: str
    data_unavailable: bool = False
    network_health_score: float
    total_devices: int
    devices_up: Optional[int] = 0
    devices_down: Optional[int] = 0
    devices_degraded: Optional[int] = 0
    active_incidents: int
    average_latency_ms: float
    packet_loss_rate: float
    message: Optional[str] = None


class RecoveryRequest(BaseModel):
    incident_id: str
    action_type: str = "auto_reroute"
    override_policy: bool = False


class RollbackRequest(BaseModel):
    recovery_action_id: Optional[Union[str, int]] = None
    action_id: Optional[Union[str, int]] = None
    incident_id: Optional[str] = None
    reason: Optional[str] = "Manual operator rollback requested"

    model_config = ConfigDict(populate_by_name=True)

    @property
    def target_action_id(self) -> str:
        aid = self.recovery_action_id if self.recovery_action_id is not None else self.action_id
        return str(aid) if aid is not None else ""


class TopologyFailRequest(BaseModel):
    link_id: Optional[str] = Field(None, description="e.g. link-s2-s3")
    target_type: Optional[str] = Field(None, description="device or link")
    target_id: Optional[str] = Field(None, description="ID of device or link")
    failure_type: Optional[str] = Field(default="link_down", description="e.g. link_down, device_down, congestion")
    link: Optional[List[str]] = Field(None, description="e.g. ['s2', 's3']")
    device: Optional[str] = Field(None, description="Device name/id")
    switch: Optional[str] = Field(None, description="Switch name, e.g. s2")
    interface: Optional[str] = Field(None, description="Interface name, e.g. s2-eth2")

    @field_validator("interface")
    @classmethod
    def validate_interface_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not re.match(r"^[a-z0-9-]+$", v):
                raise ValueError(f"Interface name '{v}' must match ^[a-z0-9-]+$")
        return v


class TopologyRestoreRequest(BaseModel):
    link_id: Optional[str] = Field(None, description="e.g. link-s2-s3")
    target_id: Optional[str] = Field(None, description="Alias for link_id")
    link: Optional[List[str]] = Field(None, description="e.g. ['s2', 's3']")


class PingRequest(BaseModel):
    host: Optional[str] = None
    host_ip: Optional[str] = None
    target: Optional[str] = None
    count: Optional[int] = 3
    timeout: Optional[float] = 2.0


class RecoveryModeRequest(BaseModel):
    mode: str = Field(..., description="autonomous, semi-autonomous, manual")


class PolicyCreateRequest(BaseModel):
    id: Optional[str] = None
    name: str
    rule_condition: str
    action_template: str
    is_active: bool = True
    priority: int = 100


class RecoveryResponse(BaseModel):
    """Honest multi-state recovery result — every field reflects what ACTUALLY happened."""
    incident_id: str
    overall_status: Literal["success", "failed", "rolled_back", "partial"]
    path_calculated: bool
    path: Optional[Dict[str, Any]] = None
    snapshot_created: bool
    snapshot_id: Optional[str] = None
    flow_installation: Literal["success", "failed", "not_started", "partial"]
    installed_flows: List[Dict[str, Any]] = []
    installation_error: Optional[str] = None
    traffic_verification: Literal["success", "failed", "not_started", "inconclusive"]
    verification_details: Optional[Dict[str, Any]] = None
    rollback_status: Literal["not_needed", "success", "failed", "not_attempted"]
    rollback_error: Optional[str] = None
    duration_ms: float
    affected_flows_count: int
    affected_flows: List[Dict[str, Any]] = []
    plans: List[Dict[str, Any]] = []
    reason: Optional[str] = None
    error: Optional[str] = None
    action_type: str = "reroute"
    affected_dpid: Optional[int] = None
    new_in_port: Optional[int] = None

    model_config = ConfigDict(populate_by_name=True)


class SimulationRequest(BaseModel):
    incident_id: str = Field(..., description="Target incident ID to simulate recovery for")


class IntegrationTestRequest(BaseModel):
    target_id: Optional[str] = Field(None, description="Optional target connector ID")
