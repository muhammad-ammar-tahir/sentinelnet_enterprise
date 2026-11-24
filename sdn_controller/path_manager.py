"""Path Management and Constrained Flow Computation for SentinelNet.

Maintains topology graphs, computes Dijkstra shortest paths with link exclusions,
maps inter-switch ports, and installs end-to-end OpenFlow 1.3 flow-mod rules.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime
import networkx as nx

logger = logging.getLogger("sentinelnet.path_manager")


class PathManager:
    """Manages SDN network topology graph, computes shortest paths, and installs path flows."""

    def __init__(self, controller=None):
        """Initialize PathManager.

        Args:
            controller: Reference to SelfHealingController instance to execute flow-mods.
        """
        self.controller = controller
        self.graph = nx.Graph()
        # Port mapping dictionary: (dpid, neighbor_dpid) -> egress_port
        self.port_map: Dict[Tuple[int, int], int] = {}
        # DPID to human-readable switch name mapping
        self.dpid_to_name: Dict[int, str] = {1: "s1", 2: "s2", 3: "s3"}
        self.name_to_dpid: Dict[str, int] = {"s1": 1, "s2": 2, "s3": 3}
        self.active_paths: List[Dict[str, Any]] = []

        self.build_topology()
        logger.info("PathManager initialized with default campus SDN topology")

    def build_topology(self) -> None:
        """Construct the university network topology graph from known link parameters.

        Topology Layout:
            s1 (Core, DPID: 1)
            s2 (Left Lab A, DPID: 2)
            s3 (Right Lab B / Server, DPID: 3)

        Physical Switch Port Allocation:
            s1: Port 1 -> s2, Port 2 -> s3
            s2: Port 1 -> s1, Port 2 -> s3 (FAILABLE), Port 3 -> h1, Port 4 -> h2
            s3: Port 1 -> s1, Port 2 -> s2 (FAILABLE), Port 3 -> h3, Port 4 -> h4, Port 5 -> srv1
        """
        self.graph.clear()
        self.port_map.clear()

        # Add nodes
        for dpid, name in self.dpid_to_name.items():
            self.graph.add_node(dpid, name=name)

        # Trunk 1: s1 <---> s2 (100 Mbps, 1ms delay, weight=1)
        self.graph.add_edge(1, 2, weight=1.0, bandwidth=100.0, delay=1.0, status="up")
        self.port_map[(1, 2)] = 1
        self.port_map[(2, 1)] = 1

        # Trunk 2: s1 <---> s3 (100 Mbps, 1ms delay, weight=1)
        self.graph.add_edge(1, 3, weight=1.0, bandwidth=100.0, delay=1.0, status="up")
        self.port_map[(1, 3)] = 2
        self.port_map[(3, 1)] = 1

        # Trunk 3 (Primary direct / FAILABLE): s2 <---> s3 (100 Mbps, 2ms delay, weight=2)
        self.graph.add_edge(2, 3, weight=2.0, bandwidth=100.0, delay=2.0, status="up")
        self.port_map[(2, 3)] = 2
        self.port_map[(3, 2)] = 2

        logger.info("Topology built: Nodes=%s, Edges=%s",
                    list(self.graph.nodes), list(self.graph.edges(data=False)))

    def _to_dpid(self, node: Any) -> int:
        """Normalize node representation to integer DPID."""
        if isinstance(node, int):
            return node
        if isinstance(node, str):
            if node.isdigit():
                return int(node)
            return self.name_to_dpid.get(node.lower(), 1)
        return 1

    def find_shortest_path(
        self,
        src_switch: Any,
        dst_switch: Any,
        exclude_links: Optional[List[Tuple[Any, Any]]] = None
    ) -> Optional[List[int]]:
        """Calculate shortest path between two switches using Dijkstra's algorithm,

        accounting for excluded (failed or congested) links.

        Args:
            src_switch: Source switch identifier (e.g. 's2' or 2).
            dst_switch: Destination switch identifier (e.g. 's3' or 3).
            exclude_links: List of link tuples to exclude, e.g. [('s2', 's3')].

        Returns:
            List of integer DPIDs representing the optimal path, or None if unreachable.
        """
        src_dpid = self._to_dpid(src_switch)
        dst_dpid = self._to_dpid(dst_switch)

        # Create temporary working graph
        working_graph = self.graph.copy()

        if exclude_links:
            for u, v in exclude_links:
                u_dpid = self._to_dpid(u)
                v_dpid = self._to_dpid(v)
                if working_graph.has_edge(u_dpid, v_dpid):
                    working_graph.remove_edge(u_dpid, v_dpid)
                    logger.info("Excluded edge (%s, %s) from routing calculation",
                                self.dpid_to_name.get(u_dpid, u_dpid),
                                self.dpid_to_name.get(v_dpid, v_dpid))

        try:
            path = nx.shortest_path(working_graph, source=src_dpid, target=dst_dpid, weight="weight")
            path_names = [self.dpid_to_name.get(d, str(d)) for d in path]
            logger.info("Computed shortest path: %s", " -> ".join(path_names))
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
            logger.warning("No feasible path exists between %s and %s: %s",
                           src_switch, dst_switch, str(exc))
            return None

    def install_path(
        self,
        path: List[int],
        match_criteria: Optional[Dict[str, Any]] = None,
        priority: int = 200,
        idle_timeout: int = 0,
        hard_timeout: int = 0
    ) -> bool:
        """Translate an end-to-end multi-hop path into individual OpenFlow 1.3 flow-mod rules

        and install them across all switches along the path.

        Detailed OpenFlow Rule Structure:
        -------------------------------------------------------------
        * Priority: High priority (e.g. 200) ensures this recovery flow
          overrides standard table-miss (0) and default MAC-learned flows (1).
        * Match Fields: Can match on Ethernet type (e.g. 0x0800 IPv4),
          source/destination MAC addresses, or incoming port.
        * Instructions / Actions: OFPActionOutput forwards packets to the
          computed next-hop egress port according to self.port_map.
        -------------------------------------------------------------

        Args:
            path: Sequence of switch DPIDs from source to destination.
            match_criteria: Packet header criteria dict.
            priority: OpenFlow rule priority level.
            idle_timeout: Seconds before inactivity eviction.
            hard_timeout: Seconds before absolute eviction.

        Returns:
            bool: True if flows were dispatched successfully.
        """
        if not path or len(path) < 2:
            logger.error("Path must contain at least 2 nodes. Given: %s", path)
            return False

        if not self.controller:
            logger.warning("Controller reference not attached. Flow rules logged only.")
            return True

        timestamp = datetime.utcnow().isoformat()
        logger.info("Installing path flows for: %s (Priority: %d)",
                    " -> ".join(self.dpid_to_name.get(d, str(d)) for d in path), priority)

        # For every hop along the path, configure forwarding to next hop
        for i in range(len(path) - 1):
            curr_dpid = path[i]
            next_dpid = path[i + 1]

            out_port = self.port_map.get((curr_dpid, next_dpid))
            if out_port is None:
                logger.error("No port mapping found between DPID %d and %d!", curr_dpid, next_dpid)
                continue

            # Forward rule
            self.controller.add_flow_rule(
                dpid=curr_dpid,
                priority=priority,
                match=match_criteria or {},
                out_port=out_port,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout,
                description=f"Reroute hop {curr_dpid}->{next_dpid} via port {out_port}"
            )

        self.active_paths.append({
            "path": [self.dpid_to_name.get(d, str(d)) for d in path],
            "dpid_path": path,
            "installed_at": timestamp,
            "priority": priority
        })
        return True

    def remove_path(self, path: List[int], match_criteria: Optional[Dict[str, Any]] = None) -> bool:
        """Remove previously installed flow rules across switches in the path."""
        logger.info("Removing flows for path: %s", path)
        if not self.controller:
            return True

        for dpid in path:
            self.controller.delete_flow_rule(dpid, match=match_criteria or {})
        return True

    def handle_link_failover(self, failed_link: Tuple[str, str]) -> Dict[str, Any]:
        """Automated failover scenario:

        When s2-s3 trunk fails, automatically compute alternative path via s1 (s2 -> s1 -> s3)
        and install high-priority OpenFlow rules.

        Args:
            failed_link: Tuple of switch names (e.g. ('s2', 's3')).

        Returns:
            Dict containing failover execution details and new path.
        """
        logger.critical(">>> INITIATING AUTOMATIC FAILOVER for link: %s <---> %s <<<",
                        failed_link[0], failed_link[1])

        u, v = failed_link[0], failed_link[1]
        u_dpid, v_dpid = self._to_dpid(u), self._to_dpid(v)

        # Mark link down in internal topology
        if self.graph.has_edge(u_dpid, v_dpid):
            self.graph[u_dpid][v_dpid]["status"] = "down"

        # Calculate new alternative path excluding the failed link
        new_path = self.find_shortest_path(u_dpid, v_dpid, exclude_links=[(u_dpid, v_dpid)])

        if not new_path:
            logger.error("Failover failed: No alternative path found between %s and %s", u, v)
            return {"status": "failed", "reason": "No feasible backup path"}

        # Install new path rules in both directions (forward and reverse)
        match_fwd = {"eth_type": 0x0800}  # IPv4 traffic
        self.install_path(new_path, match_criteria=match_fwd, priority=300)

        reverse_path = list(reversed(new_path))
        self.install_path(reverse_path, match_criteria=match_fwd, priority=300)

        path_str = " -> ".join(self.dpid_to_name.get(d, str(d)) for d in new_path)
        logger.info(">>> FAILOVER COMPLETE: Traffic successfully rerouted via %s <<<", path_str)

        return {
            "status": "success",
            "failed_link": list(failed_link),
            "new_path": [self.dpid_to_name.get(d, str(d)) for d in new_path],
            "priority": 300,
            "timestamp": datetime.utcnow().isoformat()
        }
