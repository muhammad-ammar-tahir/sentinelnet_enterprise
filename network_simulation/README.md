# SentinelNet Network Simulation Environment

The `network_simulation/` module models a multi-zone university campus Software-Defined Network (SDN) built on **Mininet**, managed by the **Ryu OpenFlow 1.3 Controller**, and equipped with an automated **Failure Injection Harness** and **Synthetic Traffic Generator**.

---

## 🏛️ Network Topology Architecture

```
                    ┌─────────────────────────┐
                    │    C0 — Ryu Controller  │
                    │      127.0.0.1:6633     │
                    └────────────┬────────────┘
                                 │ OpenFlow 1.3
           ┌─────────────────────┼─────────────────────┐
           │                     │                     │
     ┌─────▼──────┐        ┌─────▼──────┐        ┌─────▼──────┐
     │  Switch s1 │        │  Switch s2 │        │  Switch s3 │
     │  (Core)    │        │  (Lab A)   │        │  (Lab B)   │
     │  10.0.0.1  │        │  10.0.0.2  │        │  10.0.0.3  │
     └─────┬──────┘        └─────┬──────┘        └─────┬──────┘
           │                     │                     │
           ├────── Trunk L1 ─────┤                     │
           │     (100 Mbps)      │                     │
           │                     ├────── Failable ─────┤
           │                     │       Link L3       │
           │                     │     (100 Mbps)      │
           └────── Trunk L2 ───────────────────────────┤
                 (100 Mbps)                            │
                                                       │
        ┌──────────────┐                       ┌───────┴──────┐
        │  Lab A Hosts │                       │  Lab B Hosts │
        │  h1: 10.0.1.1│                       │  h3: 10.0.1.3│
        │  h2: 10.0.1.2│                       │  h4: 10.0.1.4│
        └──────────────┘                       ├──────────────┤
                                               │ Server Room  │
                                               │ srv1:10.0.0.50
                                               └──────────────┘
```

### Addressing & Port Map
| Entity | Type | IP Address | DPID / Subnet | Connected Port |
|---|---|---|---|---|
| **C0** | Ryu Controller | `127.0.0.1` | TCP:6633 / 6653 | Control Plane |
| **s1** | OpenFlow Switch | `10.0.0.1` | `0000000000000001` | Core Hub |
| **s2** | OpenFlow Switch | `10.0.0.2` | `0000000000000002` | Port 1: s1, Port 2: s3, Ports 3-4: h1-h2 |
| **s3** | OpenFlow Switch | `10.0.0.3` | `0000000000000003` | Port 1: s1, Port 2: s2, Ports 3-4: h3-h4, Port 5: srv1 |
| **h1** | Student Host | `10.0.1.1` | `255.255.255.0` | s2 (Port 3) |
| **h2** | Student Host | `10.0.1.2` | `255.255.255.0` | s2 (Port 4) |
| **h3** | Student Host | `10.0.1.3` | `255.255.255.0` | s3 (Port 3) |
| **h4** | Student Host | `10.0.1.4` | `255.255.255.0` | s3 (Port 4) |
| **srv1** | Application Server | `10.0.0.50` | `255.255.255.0` | s3 (Port 5) — 1 Gbps link |

---

## 🚀 Step-by-Step Running Guide

### 1. Prerequisites (Linux / Ubuntu VM)
```bash
sudo apt-get update
sudo apt-get install -y mininet openvswitch-switch iperf3 python3-pip
pip install ryu
```

### 2. Launch Ryu SDN Controller
Start the Ryu OpenFlow controller in a separate terminal:
```bash
ryu-manager ryu.app.simple_switch_13 ryu.app.ofctl_rest --ofp-tcp-listen-port 6633
```

### 3. Start Mininet Topology
#### Verification & Test Mode:
To quickly run an automated pingall and iperf bandwidth test:
```bash
sudo python3 network_simulation/topology.py --test
```
*Expected Output:*
```
PingAll completed with 0.00% packet loss
iperf TCP result: ['100 Mbits/sec', '95.4 Mbits/sec']
>>> VERIFICATION SUCCESSFUL: Network is fully operational. <<<
```

#### Interactive Mode (Mininet CLI):
```bash
sudo python3 network_simulation/topology.py
```
Inside the Mininet CLI:
```bash
mininet> pingall
mininet> h1 ping -c 3 srv1
mininet> exit
```

---

## ⚡ Failure Injection (Live Demos)

Run the interactive failure injection menu in another terminal:
```bash
sudo python3 network_simulation/failure_injector.py
```

### Interactive Menu Options:
1. **Kill Link (`s2 <---> s3`)**: Drops the direct primary trunk between switches s2 and s3. Demonstrates autonomous reroute via Core Switch `s1`.
2. **Kill Device (`s2` or `s3`)**: Stops switch bridge, isolating local hosts to trigger device failover alert.
3. **Inject Latency**: Adds artificial delay (e.g., 50ms) via Linux `tc netem`.
4. **Inject Packet Loss**: Causes dropped packets (e.g., 20%) to trigger Isolation Forest ML anomaly alerts.
5. **Inject Congestion**: Throttles bandwidth to 1 Mbps via Linux `tc tbf` to simulate flash crowd congestion.
6. **List Active Injections**: View currently compromised links and nodes.
7. **RESTORE ALL**: Reverts all queuing disciplines and brings all interfaces back up.

---

## 📈 Traffic Generation

Generate realistic multi-host campus traffic using `traffic_generator.py`:

```bash
# 1. Start iperf server on the academic server (srv1)
sudo python3 network_simulation/traffic_generator.py --server

# 2. Launch baseline multi-host campus traffic (h1-h4 -> srv1)
sudo python3 network_simulation/traffic_generator.py --baseline

# 3. Simulate sudden traffic spike (bursty traffic up to 85 Mbps)
sudo python3 network_simulation/traffic_generator.py --bursty --src 10.0.1.1 --dst 10.0.0.50 --rate 85.0 --duration 60
```
All throughput logs are automatically stored under `logs/traffic/`.
