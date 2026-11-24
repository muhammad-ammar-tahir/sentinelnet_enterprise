# 04 — Network Topology

## Table of Contents
1. [Topology Overview](#1-topology-overview)
2. [ASCII Diagram](#2-ascii-diagram)
3. [Device Inventory](#3-device-inventory)
4. [IP Addressing Table](#4-ip-addressing-table)
5. [Link Inventory](#5-link-inventory)
6. [Primary vs Backup Paths](#6-primary-vs-backup-paths)
7. [Mininet Configuration](#7-mininet-configuration)
8. [Failure Injection Points](#8-failure-injection-points)

---

## 1. Topology Overview

The simulated university network models a typical campus LAN divided into three logical zones:

| Zone | Switch | Connected Devices | Purpose |
|---|---|---|---|
| **Student Lab A** | S1 | H1 (Student PC), H2 (Student PC) | General computing lab |
| **Student Lab B** | S2 | H3 (Student PC), H4 (Student PC) | General computing lab |
| **Server Room** | S3 | SRV1 (Application Server) | Shared academic resources |

The **Ryu SDN Controller (C0)** manages all three switches via OpenFlow 1.3. Two backup links (S1–S3 and S2–S3) provide redundancy alongside the primary paths through S2.

---

## 2. ASCII Diagram

```
                    ┌─────────────────┐
                    │  C0 — Ryu SDN   │
                    │   Controller    │
                    │  10.0.0.254     │
                    └────────┬────────┘
                             │  OpenFlow 1.3 (TCP 6653)
          ┌──────────────────┼──────────────────┐
          │                  │                  │
    ┌─────▼──────┐     ┌─────▼──────┐     ┌─────▼──────┐
    │  S1        │     │  S2        │     │  S3        │
    │  Switch 1  │     │  Switch 2  │     │  Switch 3  │
    │  Lab A     │     │  Core      │     │  Server Rm │
    └──┬──────┬──┘     └──┬──────┬──┘     └──┬─────────┘
       │      │           │      │            │
  ─────┘      └─── L1 ───┘      └─── L2 ───┘ │
  (primary           (primary           (primary)
   path)              path)
       │                                       │
       └──────────────── BL1 ─────────────────┘
                   (Backup Link 1: S1–S3)

    S2 ──── BL2 ──── S3
       (Backup Link 2: S2–S3)

   ┌─────────────────────────────────────────────────────┐
   │  HOSTS                                              │
   │                                                     │
   │  H1 ─── S1       H3 ─── S2                         │
   │  H2 ─── S1       H4 ─── S2       SRV1 ─── S3       │
   │  10.0.0.1  10.0.0.2  10.0.0.3  10.0.0.4  10.0.0.10 │
   └─────────────────────────────────────────────────────┘

   Legend:
     L1  = Primary link: S1 ── S2  (100 Mbps, 2ms delay)
     L2  = Primary link: S2 ── S3  (100 Mbps, 2ms delay)
     BL1 = Backup link:  S1 ── S3  (50 Mbps, 5ms delay)
     BL2 = Backup link:  S2 ── S3  (50 Mbps, 5ms delay) [redundant]
```

---

## 3. Device Inventory

| ID | Type | Label | Zone | Description |
|---|---|---|---|---|
| `C0` | Controller | Ryu SDN Controller | — | OpenFlow control plane; manages all switches |
| `S1` | OVS Switch | Lab A Switch | Student Lab A | Connects H1, H2 to network core |
| `S2` | OVS Switch | Core Switch | Core | Connects labs to server room; primary aggregation point |
| `S3` | OVS Switch | Server Room Switch | Server Room | Connects SRV1; terminates both backup links |
| `H1` | Mininet Host | Student PC 1 | Student Lab A | Simulates a student workstation |
| `H2` | Mininet Host | Student PC 2 | Student Lab A | Simulates a student workstation |
| `H3` | Mininet Host | Student PC 3 | Student Lab B | Simulates a student workstation |
| `H4` | Mininet Host | Student PC 4 | Student Lab B | Simulates a student workstation |
| `SRV1` | Mininet Host | App/File Server | Server Room | Simulates a shared academic server (iperf, HTTP) |

---

## 4. IP Addressing Table

| Device | Interface | IP Address | Subnet | Gateway | MAC Prefix |
|---|---|---|---|---|---|
| H1 | h1-eth0 | 10.0.0.1 | /24 | 10.0.0.254 | 00:00:00:00:00:01 |
| H2 | h2-eth0 | 10.0.0.2 | /24 | 10.0.0.254 | 00:00:00:00:00:02 |
| H3 | h3-eth0 | 10.0.0.3 | /24 | 10.0.0.254 | 00:00:00:00:00:03 |
| H4 | h4-eth0 | 10.0.0.4 | /24 | 10.0.0.254 | 00:00:00:00:00:04 |
| SRV1 | srv1-eth0 | 10.0.0.10 | /24 | 10.0.0.254 | 00:00:00:00:00:10 |
| C0 (Ryu) | — | 10.0.0.254 | — | — | — |
| S1 | lo | 10.0.1.1 | /32 | — | — |
| S2 | lo | 10.0.1.2 | /32 | — | — |
| S3 | lo | 10.0.1.3 | /32 | — | — |

> **Note:** Switches don't have IP addresses in the data plane (they're Layer 2). The loopback IPs above are management addresses used by Ryu for switch identification.

---

## 5. Link Inventory

| Link ID | From | To | Type | Bandwidth | Delay | Loss | Role |
|---|---|---|---|---|---|---|---|
| L1 | S1 (port 3) | S2 (port 1) | Copper | 100 Mbps | 2 ms | 0% | **Primary** — Lab A to Core |
| L2 | S2 (port 2) | S3 (port 1) | Copper | 100 Mbps | 2 ms | 0% | **Primary** — Core to Server Room |
| BL1 | S1 (port 4) | S3 (port 2) | Copper | 50 Mbps | 5 ms | 0% | **Backup** — Lab A direct to Server Room |
| BL2 | S2 (port 3) | S3 (port 3) | Copper | 50 Mbps | 5 ms | 0% | **Backup** — Core alternate to Server Room |
| H1-S1 | H1 (eth0) | S1 (port 1) | Virtual | 1 Gbps | 1 ms | 0% | Access link |
| H2-S1 | H2 (eth0) | S1 (port 2) | Virtual | 1 Gbps | 1 ms | 0% | Access link |
| H3-S2 | H3 (eth0) | S2 (port 4) | Virtual | 1 Gbps | 1 ms | 0% | Access link |
| H4-S2 | H4 (eth0) | S2 (port 5) | Virtual | 1 Gbps | 1 ms | 0% | Access link |
| SRV1-S3 | SRV1 (eth0) | S3 (port 4) | Virtual | 1 Gbps | 1 ms | 0% | Server access link |

---

## 6. Primary vs Backup Paths

### Path: H1 → SRV1 (Primary)

```
H1 → S1 → [L1] → S2 → [L2] → S3 → SRV1

Hops: 3 switches
Bandwidth: min(100 Mbps, 100 Mbps) = 100 Mbps
Latency:   1ms + 2ms + 1ms + 2ms + 1ms = ~7ms RTT
```

**OpenFlow rules (primary):**
- S1: `match dst=10.0.0.10 → output port 3` (toward S2)
- S2: `match dst=10.0.0.10 → output port 2` (toward S3)
- S3: `match dst=10.0.0.10 → output port 4` (toward SRV1)

---

### Path: H1 → SRV1 (Backup — via BL1 when L1 fails)

```
H1 → S1 → [BL1] → S3 → SRV1

Hops: 2 switches
Bandwidth: 50 Mbps (backup link constraint)
Latency:   1ms + 5ms + 1ms = ~7ms RTT (similar due to fewer hops)
```

**Trigger:** BL1 activates when Ryu detects `port_status=DOWN` on S1 port 3 (L1).

**Recovery:** SentinelNet's `RecoveryExecutor` calls Ryu to modify S1 flow rules: `match dst=10.0.0.10 → output port 4` (toward BL1 instead of L1).

---

### Path: H3/H4 → SRV1 (Backup — via BL2 when L2 fails)

```
H3 → S2 → [BL2] → S3 → SRV1

Hops: 2 switches
Bandwidth: 50 Mbps
```

---

### Path Summary Table

| Source | Destination | Primary Path | Backup Path | Trigger |
|---|---|---|---|---|
| H1, H2 | SRV1 | H→S1→S2→S3→SRV1 | H→S1→(BL1)→S3→SRV1 | L1 down |
| H3, H4 | SRV1 | H→S2→S3→SRV1 | H→S2→(BL2)→S3→SRV1 | L2 down |
| H1, H2 | H3, H4 | H→S1→S2→H | H→S1→(BL1)→S3→(BL2)→S2→H | L1 + partial S2 failure |
| Any host | SRV1 | Shortest via S2 | Via backup links | Any primary failure |

---

## 7. Mininet Configuration

The topology is implemented in `network_simulation/topology.py` using the `UniversityTopology` class. Key parameters:

```python
# network_simulation/topology.py

from mininet.topo import Topo
from mininet.node import OVSSwitch
from mininet.link import TCLink

class UniversityTopology(Topo):
    def build(self):
        # OpenFlow 1.3 Switches
        s1 = self.addSwitch("s1", dpid="0000000000000001", protocols="OpenFlow13", ip="10.0.0.1")
        s2 = self.addSwitch("s2", dpid="0000000000000002", protocols="OpenFlow13", ip="10.0.0.2")
        s3 = self.addSwitch("s3", dpid="0000000000000003", protocols="OpenFlow13", ip="10.0.0.3")

        # Student Lab Hosts & Academic Server
        h1 = self.addHost("h1", ip="10.0.1.1/24", mac="00:00:00:00:01:01")
        h2 = self.addHost("h2", ip="10.0.1.2/24", mac="00:00:00:00:01:02")
        h3 = self.addHost("h3", ip="10.0.1.3/24", mac="00:00:00:00:01:03")
        h4 = self.addHost("h4", ip="10.0.1.4/24", mac="00:00:00:00:01:04")
        srv1 = self.addHost("srv1", ip="10.0.0.50/24", mac="00:00:00:00:00:50")

        # Inter-Switch Links
        self.addLink(s1, s2, port1=1, port2=1, bw=100, delay="1ms")  # Primary Trunk L1
        self.addLink(s1, s3, port1=2, port2=1, bw=100, delay="1ms")  # Primary Trunk L2
        self.addLink(s2, s3, port1=2, port2=2, bw=100, delay="2ms")  # Failable Trunk L3

        # Host & Server Links
        self.addLink(h1, s2, port1=0, port2=3, bw=100, delay="1ms")
        self.addLink(h2, s2, port1=0, port2=4, bw=100, delay="1ms")
        self.addLink(h3, s3, port1=0, port2=3, bw=100, delay="1ms")
        self.addLink(h4, s3, port1=0, port2=4, bw=100, delay="1ms")
        self.addLink(srv1, s3, port1=0, port2=5, bw=1000, delay="0.5ms")
```

---

## 8. Failure Injection Points

| Fault ID | Type | Command | Expected Trigger |
|---|---|---|---|
| F1 | Link failure (L1) | `net.configLinkStatus('s1', 's2', 'down')` | `LINK_FAILURE` on L1 |
| F2 | Congestion on L2 | `h3.cmd('iperf -c 10.0.0.10 -b 95M -t 60')` | `CONGESTION` on L2 |
| F3 | High latency (BL1) | `tc qdisc add dev s1-eth4 root netem delay 200ms` | `HIGH_LATENCY` |
| F4 | Device failure (S2) | `s2.stop()` | `DEVICE_FAILURE` on S2 |
| F5 | Repeated link flap | Loop `F1` 3× in 2 minutes | `REPEATED_FAILURE` escalation |

All injection commands are automated in `network_simulation/failure_injector.py` via programmatic API or interactive CLI:

```bash
# Launch interactive fault injection console:
sudo python network_simulation/failure_injector.py
```
