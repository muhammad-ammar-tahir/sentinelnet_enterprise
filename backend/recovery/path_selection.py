"""backend/recovery/path_selection.py — Constrained Optimization Path Selection.

Calculates constraint-satisfying alternative routing paths across the network topology
using NetworkX Dijkstra weighted by latency, packet loss, and link utilization.
Maps paths to actual switch DPIDs and OpenFlow physical port numbers.
"""

import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional, Tuple, Set
import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class Hop:
    """Individual switch forwarding hop along a path."""
    dpid: int
    switch_name: str
    in_port: int
    out_port: int
    next_hop: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PathResult:
    """Path computation result."""
    found: bool
    path: List[str]                      # Sequence of device/switch names: ["h1", "s1", "s3", "srv1"]
    hops: List[Dict[str, Any]]           # Detailed switch hop configs with dpid and ports
    predicted_latency_ms: float
    predicted_loss_pct: float
    reason: str                          # Reason for selection or failure explanation

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PathSelector:
    """Computes constraint-satisfying alternative routing paths across the network topology."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self._devices_by_id: Dict[str, Dict[str, Any]] = {}
        self._links: List[Dict[str, Any]] = []
        logger.info("PathSelector initialized with NetworkX graph engine")

    def build_topology_graph(
        self,
        devices: List[Dict[str, Any]],
        links: List[Dict[str, Any]],
        metrics: Optional[Dict[str, Any]] = None
    ) -> None:
        """Construct weighted graph representation from database/telemetry state.

        Args:
            devices: List of device dicts (id, device_type, dpid, etc.).
            links: List of link dicts (id, src_device_id, dst_device_id, src_port, dst_port, etc.).
            metrics: Optional dynamic metrics dict keyed by link_id or device_id.
        """
        self.graph.clear()
        self._devices_by_id = {d["id"]: d for d in devices}
        self._links = links

        for dev in devices:
            self.graph.add_node(dev["id"], **dev)

        for link in links:
            src = link["src_device_id"]
            dst = link["dst_device_id"]

            # Edge cost calculation: latency + (loss * 100) + load_penalty
            latency = float(link.get("latency_ms") or 1.0)
            loss_pct = float(link.get("packet_loss_rate") or link.get("loss_pct") or 0.0)
            utilization = float(link.get("current_utilization") or link.get("utilization") or 0.0)
            bandwidth = float(link.get("bandwidth_mbps") or 100.0)

            # Weight = latency + (loss_pct * 10.0) + (utilization / 100.0 * 20.0)
            weight = latency + (loss_pct * 10.0) + ((utilization / 100.0) ** 2 * 25.0)

            # Add both forward and reverse edges for full-duplex physical Ethernet links
            self.graph.add_edge(
                src,
                dst,
                id=link.get("id"),
                weight=weight,
                latency=latency,
                loss_pct=loss_pct,
                bandwidth=bandwidth,
                src_port=link.get("src_port", 1),
                dst_port=link.get("dst_port", 1),
                status=link.get("status", "up")
            )
            self.graph.add_edge(
                dst,
                src,
                id=link.get("id"),
                weight=weight,
                latency=latency,
                loss_pct=loss_pct,
                bandwidth=bandwidth,
                src_port=link.get("dst_port", 1),
                dst_port=link.get("src_port", 1),
                status=link.get("status", "up")
            )

        logger.debug(
            "Topology graph built: %d nodes, %d directed edges",
            self.graph.number_of_nodes(), self.graph.number_of_edges()
        )

    def _find_link(self, u: str, v: str) -> Optional[Dict[str, Any]]:
        """Find link dictionary connecting u -> v."""
        for l in self._links:
            if l.get("src_device_id") == u and l.get("dst_device_id") == v:
                return l
            # If links are bi-directional representation:
            if l.get("src_device_id") == v and l.get("dst_device_id") == u:
                return {
                    "id": l.get("id"),
                    "src_device_id": u,
                    "dst_device_id": v,
                    "src_port": l.get("dst_port"),
                    "dst_port": l.get("src_port"),
                    "bandwidth_mbps": l.get("bandwidth_mbps", 100.0),
                    "latency_ms": l.get("latency_ms", 1.0),
                    "status": l.get("status", "up")
                }
        return None

    def _resolve_hops(self, path: List[str]) -> List[Dict[str, Any]]:
        """Map a node sequence to OpenFlow switch hops with explicit DPIDs and ports."""
        hops: List[Dict[str, Any]] = []

        for i in range(len(path)):
            curr_node = path[i]
            dev_meta = self._devices_by_id.get(curr_node, {})

            # Only switches execute OpenFlow flow hops
            if dev_meta.get("device_type") != "switch":
                continue

            prev_node = path[i - 1] if i > 0 else None
            next_node = path[i + 1] if i < len(path) - 1 else None

            # Resolve in_port from link connecting prev_node -> curr_node
            in_port = 1
            if prev_node:
                edge_data = self.graph.get_edge_data(prev_node, curr_node)
                if edge_data:
                    in_port = edge_data.get("dst_port", 1)
                else:
                    link_obj = self._find_link(prev_node, curr_node)
                    if link_obj:
                        in_port = link_obj.get("dst_port", 1)

            # Resolve out_port from link connecting curr_node -> next_node
            out_port = 2
            if next_node:
                edge_data = self.graph.get_edge_data(curr_node, next_node)
                if edge_data:
                    out_port = edge_data.get("src_port", 2)
                else:
                    link_obj = self._find_link(curr_node, next_node)
                    if link_obj:
                        out_port = link_obj.get("src_port", 2)

            dpid_raw = dev_meta.get("dpid") or dev_meta.get("openflow_dpid") or 1
            try:
                # Handle hex string or integer DPID
                if isinstance(dpid_raw, str):
                    dpid = int(dpid_raw, 16) if dpid_raw.startswith("0x") or len(dpid_raw) > 8 else int(dpid_raw)
                else:
                    dpid = int(dpid_raw)
            except ValueError:
                # Fallback switch index: 's1' -> 1, 's2' -> 2
                digits = "".join(filter(str.isdigit, curr_node))
                dpid = int(digits) if digits else 1

            hops.append({
                "dpid": dpid,
                "switch_name": curr_node,
                "in_port": in_port,
                "out_port": out_port,
                "next_hop": next_node or "destination"
            })

        return hops

    def find_optimal_path(
        self,
        src_device: str,
        dst_device: str,
        exclude_links: Optional[List[Tuple[str, str]]] = None,
        constraints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Uses Dijkstra weighted by latency, packet loss, and utilization penalty.

        Excludes failed links and enforces min_bandwidth & max_latency constraints.
        Returns:
            {
              "found": bool,
              "path": ["s1", "s3"],
              "hops": [
                {"dpid": 1, "in_port": 2, "out_port": 3, "next_hop": "s3"}, ...
              ],
              "predicted_latency_ms": float,
              "predicted_loss_pct": float,
              "reason": str
            }
        """
        exclude_links = exclude_links or []
        constraints = constraints or {}
        min_bw = float(constraints.get("min_bandwidth", 0.0))
        max_lat = float(constraints.get("max_latency", 999999.0))

        logger.info(
            "Computing optimal path %s -> %s (exclude=%s, min_bw=%.1f, max_lat=%.1f)",
            src_device, dst_device, exclude_links, min_bw, max_lat
        )

        # 1. Build a working copy of graph with exclusions
        working_graph = self.graph.copy()

        # Remove excluded links (in both directions for physical links)
        for u, v in exclude_links:
            if working_graph.has_edge(u, v):
                working_graph.remove_edge(u, v)
            if working_graph.has_edge(v, u):
                working_graph.remove_edge(v, u)

        # Remove edges that violate bandwidth or down status constraints
        edges_to_remove = []
        for u, v, data in working_graph.edges(data=True):
            if data.get("status") == "down":
                edges_to_remove.append((u, v))
            elif data.get("bandwidth", 100.0) < min_bw:
                edges_to_remove.append((u, v))

        for u, v in edges_to_remove:
            working_graph.remove_edge(u, v)

        if not working_graph.has_node(src_device) or not working_graph.has_node(dst_device):
            return PathResult(
                found=False,
                path=[],
                hops=[],
                predicted_latency_ms=0.0,
                predicted_loss_pct=100.0,
                reason="no_alternate_path_available: source or destination node not present in topology"
            ).to_dict()

        # 2. Run Dijkstra on remaining graph
        try:
            path = nx.shortest_path(working_graph, source=src_device, target=dst_device, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            logger.warning("No alternate path found between %s and %s", src_device, dst_device)
            return PathResult(
                found=False,
                path=[],
                hops=[],
                predicted_latency_ms=0.0,
                predicted_loss_pct=100.0,
                reason="no_alternate_path_available"
            ).to_dict()

        # 3. Calculate accumulated metrics along chosen path
        total_latency = 0.0
        total_loss = 0.0
        for i in range(len(path) - 1):
            edge_data = working_graph.get_edge_data(path[i], path[i + 1]) or {}
            total_latency += edge_data.get("latency", 1.0)
            total_loss += edge_data.get("loss_pct", 0.0)

        # Enforce max_latency constraint on total path
        if total_latency > max_lat:
            logger.warning(
                "Shortest path latency (%.2fms) exceeds max_latency constraint (%.2fms)",
                total_latency, max_lat
            )
            return PathResult(
                found=False,
                path=[],
                hops=[],
                predicted_latency_ms=round(total_latency, 2),
                predicted_loss_pct=round(total_loss, 2),
                reason=f"latency_constraint_violated: path latency {total_latency:.1f}ms > {max_lat:.1f}ms"
            ).to_dict()

        # 4. Resolve hops with DPIDs and physical ports
        hops = self._resolve_hops(path)

        reason = (
            f"optimal_dijkstra_path: {len(path)} nodes, {len(hops)} switch hops, "
            f"predicted latency {total_latency:.2f}ms, loss {total_loss:.2f}%"
        )

        logger.info("Found path %s -> %s: %s", src_device, dst_device, " -> ".join(path))

        return PathResult(
            found=True,
            path=path,
            hops=hops,
            predicted_latency_ms=round(total_latency, 2),
            predicted_loss_pct=round(total_loss, 2),
            reason=reason
        ).to_dict()

    def evaluate_all_paths(self, src: str, dst: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return ALL possible simple paths between src and dst ranked by predicted quality."""
        if not self.graph.has_node(src) or not self.graph.has_node(dst):
            return []

        try:
            paths = list(nx.all_simple_paths(self.graph, source=src, target=dst, cutoff=6))
        except Exception:
            return []

        ranked_results = []
        for p in paths:
            total_lat = 0.0
            total_loss = 0.0
            for i in range(len(p) - 1):
                edge = self.graph.get_edge_data(p[i], p[i + 1]) or {}
                total_lat += edge.get("latency", 1.0)
                total_loss += edge.get("loss_pct", 0.0)

            hops = self._resolve_hops(p)
            ranked_results.append({
                "found": True,
                "path": p,
                "hops": hops,
                "predicted_latency_ms": round(total_lat, 2),
                "predicted_loss_pct": round(total_loss, 2),
                "hop_count": len(hops)
            })

        # Rank ascending by latency then hop count
        ranked_results.sort(key=lambda x: (x["predicted_latency_ms"], x["hop_count"]))
        return ranked_results[:limit]
