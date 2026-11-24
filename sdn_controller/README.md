# SentinelNet Ryu SDN Controller Application

The `sdn_controller/` module contains the centralized Software-Defined Networking (SDN) controller application built on the **Ryu OpenFlow Framework (OpenFlow 1.3)**. It provides autonomous MAC learning, dynamic shortest-path rerouting via **NetworkX**, and REST API endpoints for external self-healing orchestration.

---

## 🏗️ Architecture & OpenFlow 1.3 Flow Structure

### OpenFlow Rule Hierarchy & Pipeline
SentinelNet implements a strict priority-based flow table pipeline:

| Priority | Rule Type | Match Criteria | Actions | Purpose |
|---|---|---|---|---|
| **0** | **Table-Miss** | None (Match all) | `OUTPUT:CONTROLLER` | Forwards unknown packet headers to Ryu via `OFPT_PACKET_IN`. |
| **1** | **MAC Forwarding** | `in_port`, `eth_dst` | `OUTPUT:port` | Learned Layer-2 direct host forwarding with 30s idle timeout. |
| **200** | **Engine Reroute** | `eth_type: 0x0800` (IPv4) | `OUTPUT:backup_port` | Dynamic alternative path installed by Recovery Engine. |
| **300** | **Emergency Failover** | `eth_type: 0x0800` (IPv4) | `OUTPUT:s1_port` | Immediate reroute bypass when primary trunk `s2-s3` fails. |

```
                       ┌────────────────────────────────────────┐
                       │        Incoming Packet on Switch       │
                       └───────────────────┬────────────────────┘
                                           │
                       ┌───────────────────▼────────────────────┐
                       │ Matches Emergency Failover (Priority 300)│───► Forward via Backup Link
                       └───────────────────┬────────────────────┘
                                           │ No match
                       ┌───────────────────▼────────────────────┐
                       │ Matches Learned Flow (Priority 1)      │───► Forward Direct to Host
                       └───────────────────┬────────────────────┘
                                           │ No match
                       ┌───────────────────▼────────────────────┐
                       │ Table-Miss Entry (Priority 0)          │───► Send to Ryu via PacketIn
                       └────────────────────────────────────────┘
```

---

## 🚀 Running the Controller

### 1. Prerequisites
Ensure Ryu is installed in your Python environment:
```bash
pip install ryu eventlet==0.30.2 networkx webob
```

### 2. Launch the Application
Run `ryu_app.py` with `ryu-manager`:
```bash
ryu-manager ryu.app.ofctl_rest sdn_controller/ryu_app.py \
  --observe-links \
  --ofp-tcp-listen-port 6633 \
  --wsapi-port 8080 \
  --verbose
```
*Port allocations:*
- `6633` (or `6653`): OpenFlow TCP listening port for Mininet switches.
- `8080`: WSGI HTTP REST API listening port for backend integration (supports standard `ofctl_rest` endpoints `/stats/switches`, `/stats/flow/<dpid>`, `/stats/flowentry/add`, etc.).

---

## 🔌 Backend Client Integration (`backend/controller/sdn_controller.py`)

The backend interacts with Ryu via `RyuSDNControllerClient`:
- **Real HTTP interactions**: Uses `httpx.AsyncClient` targeting `RYU_URL` (default: `http://127.0.0.1:8080`).
- **Active Post-Installation Verification**: Every flow addition/modification/deletion immediately calls `get_flows(dpid)` to verify that the flow table actually matches the requested rule.
- **Fail-Fast Error Handling**: Raises `ControllerUnavailable` when Ryu is down and `VerificationFailed` if a flow rule was not applied. Never returns a fake `True`.
- **Automatic Retries**: Implements 2 retries with exponential backoff on transient network and 5xx errors; 4xx client errors fail immediately without retry.

Test the backend-to-Ryu connection via CLI:
```bash
python backend/controller/sdn_controller.py
```

---

## 🌐 REST API Endpoints & `curl` Testing

The controller exposes RESTful endpoints for real-time flow interrogation and dynamic mitigation:

### 1. Trigger Flow Reroute (`POST /reroute`)
Instructs the controller that a link has failed and to compute & install alternative paths:
```bash
curl -X POST http://localhost:8080/reroute \
  -H "Content-Type: application/json" \
  -d '{
    "failed_link": ["s2", "s3"],
    "new_path": [["s1", "s3"]]
  }'
```
*Example JSON Response:*
```json
{
  "status": "success",
  "failed_link": ["s2", "s3"],
  "new_path": ["s2", "s1", "s3"],
  "priority": 300,
  "timestamp": "2026-11-22T18:42:00.123456"
}
```

### 2. Inspect Flow Rules & Learned MACs (`GET /flows`)
Retrieve current flow state, connected switch DPIDs, and learned host addresses:
```bash
curl -X GET http://localhost:8080/flows
```
*Example JSON Response:*
```json
{
  "connected_switches": [1, 2, 3],
  "learned_macs": {
    "2": {
      "00:00:00:00:01:01": 3,
      "00:00:00:00:01:02": 4
    },
    "3": {
      "00:00:00:00:00:50": 5
    }
  },
  "active_failover_paths": [
    {
      "path": ["s2", "s1", "s3"],
      "dpid_path": [2, 1, 3],
      "installed_at": "2026-11-22T18:42:00.123456",
      "priority": 300
    }
  ],
  "recent_flow_history": [
    {
      "timestamp": "2026-11-22T18:42:00.120000",
      "action": "FLOW_ADD",
      "dpid": 2,
      "priority": 300,
      "description": "Reroute hop 2->1 via port 1"
    }
  ]
}
```

### 3. Flush Flow Tables (`DELETE /flows`)
Clears all installed dynamic and reroute flow rules across all switches and reinstalls table-miss baselines:
```bash
curl -X DELETE http://localhost:8080/flows
```
*Example JSON Response:*
```json
{
  "status": "success",
  "message": "All flows cleared"
}
```
