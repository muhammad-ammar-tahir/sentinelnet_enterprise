# 01 — Project Overview

## Table of Contents
1. [Problem Statement](#1-problem-statement)
2. [Proposed Solution](#2-proposed-solution)
3. [Objectives](#3-objectives)
4. [Project Scope](#4-project-scope)
5. [Out of Scope](#5-out-of-scope)
6. [Expected Outcomes](#6-expected-outcomes)
7. [Academic Context](#7-academic-context)

---

## 1. Problem Statement

Modern computer networks — including those in universities, hospitals, and enterprises — are growing in complexity faster than human operators can manage them. When a failure occurs (a broken link, overloaded switch, or misbehaving device), the typical response cycle looks like this:

```
Failure occurs
    → Monitoring alert fires (1–5 minutes delay)
    → NOC engineer is paged
    → Engineer diagnoses root cause manually (5–30 minutes)
    → Engineer executes a fix (another 5–15 minutes)
    → System verified manually
    → Incident closed
```

**Total mean time to repair (MTTR): 15 minutes to several hours.**

This delay is unacceptable for time-sensitive applications. Beyond slow response, networks face:

- **Reactive-only management** — problems are fixed after they cause disruption, not before
- **Alert fatigue** — monitoring systems produce thousands of low-quality alerts, burying real problems
- **Knowledge silos** — recovery decisions depend on specific engineers' institutional memory
- **No learning** — the same failure types recur because there is no feedback loop from past incidents

For a university campus network specifically, failures during exams, online assessments, or research data transfers can have direct academic and financial consequences.

---

## 2. Proposed Solution

**SentinelNet** is an AI-powered self-healing network management system built on Software-Defined Networking (SDN) principles. It replaces the manual detection-diagnosis-recovery loop with an automated closed-loop pipeline:

```
Continuous Monitoring
    → AI-based Anomaly Detection (Isolation Forest)
    → Automated Root-Cause Diagnosis (Classifier)
    → ML-driven Recovery Recommendation
    → Automated Recovery Execution (via Ryu SDN controller)
    → Automated Verification
    → Feedback into training data
```

**Key idea:** SDN separates the network control plane from the data plane. The Ryu controller has a programmatic API over the entire network — it can read link states, install new flow rules, reroute traffic, and throttle bandwidth in milliseconds. SentinelNet places an AI layer on top of this control plane to make intelligent, automatic decisions.

### Why SDN + AI?

| Traditional Network | SDN + AI (SentinelNet) |
|---|---|
| Distributed, closed-box control | Centralized, programmable control plane |
| Manual CLI-based fixes | Automated flow rule updates |
| Threshold alerts only | Statistical anomaly detection |
| No failure prediction | Proactive failure prediction |
| No recovery knowledge base | ML-based recovery recommendations |
| No feedback loop | Continuous model retraining |

---

## 3. Objectives

### Primary Objectives

1. **Implement real-time monitoring** of a simulated university network using Mininet and Prometheus, capturing packet loss, latency, throughput, CPU, and flow table utilization at 10-second intervals.

2. **Build an anomaly detection module** using Isolation Forest that flags abnormal network states with a target false positive rate below 10%.

3. **Develop a failure classification module** that identifies the root cause of a detected anomaly from among the 5 defined failure types with >80% accuracy.

4. **Implement 5 automated recovery actions** (link failover, traffic rerouting, rate limiting, device restart simulation, policy escalation) executable through the Ryu OpenFlow API.

5. **Create a React-based NOC dashboard** that displays the live topology, active incidents, AI confidence scores, and recovery history.

6. **Measure system performance** against defined KPIs: detection time <30s, recovery time <60s, availability >99%, false positive rate <10%.

### Secondary Objectives

7. Build a PostgreSQL-backed incident log and policy database that records every detected anomaly, diagnosis, action taken, and outcome.

8. Document a reproducible experimental setup so results can be independently verified.

9. Identify limitations honestly and propose future work for a production-grade system.

---

## 4. Project Scope

### In Scope

| Area | What's Included |
|---|---|
| **Network simulation** | Mininet topology with 1 controller, 3 OpenFlow switches, 4 hosts, 1 server, 2 redundant backup links |
| **Monitoring** | Prometheus scraping Ryu and Mininet exporters; 10s collection interval |
| **AI — Detection** | Isolation Forest anomaly detection on 8 network metrics |
| **AI — Diagnosis** | Random Forest classifier for 5 failure type labels |
| **AI — Recommendation** | Rule-based + ML hybrid recovery recommendation |
| **Recovery execution** | Automated via Ryu REST API: rerouting, rate-limiting, failover |
| **Verification** | Re-check metrics post-recovery, mark incident resolved or escalate |
| **Backend** | FastAPI REST + WebSocket API, PostgreSQL storage, Redis pub/sub |
| **Frontend** | React NOC dashboard: topology map, incident list, AI feed, graphs |
| **Evaluation** | Controlled experiments injecting 5 failure types, measuring KPIs |

### 5. Out of Scope

- **Real physical hardware** — all networking is simulated in Mininet
- **Multi-tenant or cloud deployments** — single-instance local setup only
- **Production-grade security hardening** — authentication is included but not penetration-tested
- **Large-scale topologies** (>20 nodes) — not evaluated in this project
- **BGP, OSPF or dynamic routing protocols** — only OpenFlow-managed static and reactive flows
- **NLP-based alert summarization** — out of scope for semester timeline

---

## 6. Expected Outcomes

By the end of the semester, the project should demonstrate:

| Outcome | Success Criterion |
|---|---|
| Automated anomaly detection | Isolation Forest detects injected faults within 30 seconds |
| Failure classification | Correct failure type identified ≥80% of the time |
| Automated recovery | Recovery action executed and network stable within 60 seconds of detection |
| System availability | Simulated uptime ≥99% across 1-hour continuous experiment |
| False positive rate | <10% spurious alerts during normal (non-fault) operation |
| Dashboard usability | NOC operator can read incident details and trigger manual recovery in <3 clicks |
| Reproducibility | Another student can follow docs/09-DEPLOYMENT.md and reproduce all 5 experiments |

---

## 7. Academic Context

| Field | Value |
|---|---|
| **Course** | Final Year / Semester Project — Computer Networks / AI Systems |
| **Institution** | University (name redacted) |
| **Technologies** | Python, Mininet, Ryu, Scikit-learn, FastAPI, React, PostgreSQL |
| **Team size** | 1–4 students |
| **Timeline** | 1 semester (~16 weeks) |
| **Deliverables** | Working demo, codebase, documentation, evaluation report |

This project sits at the intersection of **Software-Defined Networking (SDN)**, **machine learning for anomaly detection**, and **network reliability engineering**. It is intentionally scoped to a university network environment because:

1. University networks are realistic but bounded in scale
2. The failure types (link cuts, congestion during peak hours, lab server overload) are well-understood
3. Mininet can faithfully simulate the topology in a laptop environment
4. The evaluation can be controlled (fault injection is deterministic)

> **Honest disclaimer:** This is a simulation-based research prototype. Results achieved in Mininet will not automatically generalize to production networks with physical hardware, proprietary vendor firmware, or internet-scale traffic. The gap between simulation and production is explicitly acknowledged and discussed in [10-TESTING-EVALUATION.md](10-TESTING-EVALUATION.md).
