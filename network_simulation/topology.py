"""Custom Mininet University Network Topology for SentinelNet.

Defines the `UniversityTopology` class modeling a university campus SDN with:
- 1 Remote Ryu SDN Controller (127.0.0.1:6633 / 6653)
- 3 OpenFlow 1.3 Switches:
    * s1: Core Switch (IP: 10.0.0.1)
    * s2: Left Aggregation Switch (IP: 10.0.0.2)
    * s3: Right Aggregation Switch (IP: 10.0.0.3)
- 4 Student Lab Hosts:
    * h1, h2: Under Switch s2 (IPs: 10.0.1.1, 10.0.1.2)
    * h3, h4: Under Switch s3 (IPs: 10.0.1.3, 10.0.1.4)
- 1 Server:
    * srv1: Academic Application & File Server under s3 (IP: 10.0.0.50)
- Links:
    * s1 - s2: Primary Trunk (100 Mbps, 1ms delay)
    * s1 - s3: Primary Trunk (100 Mbps, 1ms delay)
    * s2 - s3: Cross-link / FAILABLE Link (100 Mbps, 2ms delay)
    * Hosts/Server links to respective switches

Supports standalone execution with `--test` verification mode (pingall + iperf).
"""

import sys
import argparse
import logging
from typing import Dict, Any, Optional

try:
    from mininet.topo import Topo
    from mininet.net import Mininet
    from mininet.node import RemoteController, OVSSwitch, Host
    from mininet.link import TCLink
    from mininet.cli import CLI
    from mininet.log import setLogLevel, info, error
except ImportError:
    # Graceful fallback when imported outside a Mininet Linux environment (e.g., local IDE/linting)
    class Topo:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass
        def addSwitch(self, name, **opts): return name
        def addHost(self, name, **opts): return name
        def addLink(self, node1, node2, **opts): return (node1, node2)

    Mininet = None
    RemoteController = None
    OVSSwitch = None
    Host = None
    TCLink = None
    CLI = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinelnet.topology")


class UniversityTopology(Topo):
    """Custom University Campus SDN Topology for SentinelNet Self-Healing Network."""

    def build(self, **_opts) -> None:
        """Construct the switches, hosts, servers, and inter-switch link mesh."""
        logger.info("Building SentinelNet University Topology...")

        # -----------------------------------------------------------------
        # 1. OpenFlow 1.3 Switches
        # -----------------------------------------------------------------
        # Core Switch (s1)
        s1 = self.addSwitch(
            "s1",
            dpid="0000000000000001",
            protocols="OpenFlow13",
            ip="10.0.0.1"
        )
        # Left Distribution Switch (s2) - Student Lab A
        s2 = self.addSwitch(
            "s2",
            dpid="0000000000000002",
            protocols="OpenFlow13",
            ip="10.0.0.2"
        )
        # Right Distribution Switch (s3) - Server Room & Lab B
        s3 = self.addSwitch(
            "s3",
            dpid="0000000000000003",
            protocols="OpenFlow13",
            ip="10.0.0.3"
        )

        # -----------------------------------------------------------------
        # 2. Hosts & Servers
        # -----------------------------------------------------------------
        # Student Lab A hosts connected to Switch s2
        h1 = self.addHost(
            "h1",
            ip="10.0.1.1/24",
            mac="00:00:00:00:01:01",
            defaultRoute="via 10.0.1.254"
        )
        h2 = self.addHost(
            "h2",
            ip="10.0.1.2/24",
            mac="00:00:00:00:01:02",
            defaultRoute="via 10.0.1.254"
        )

        # Student Lab B hosts connected to Switch s3
        h3 = self.addHost(
            "h3",
            ip="10.0.1.3/24",
            mac="00:00:00:00:01:03",
            defaultRoute="via 10.0.1.254"
        )
        h4 = self.addHost(
            "h4",
            ip="10.0.1.4/24",
            mac="00:00:00:00:01:04",
            defaultRoute="via 10.0.1.254"
        )

        # Central Application & Academic File Server connected to Switch s3
        srv1 = self.addHost(
            "srv1",
            ip="10.0.0.50/24",
            mac="00:00:00:00:00:50",
            defaultRoute="via 10.0.0.254"
        )

        # -----------------------------------------------------------------
        # 3. Inter-Switch Links
        # -----------------------------------------------------------------
        # Primary Trunk: s1 (Core) <---> s2 (Left Lab A)
        self.addLink(
            s1, s2,
            port1=1, port2=1,
            bw=100,
            delay="1ms",
            loss=0,
            max_queue_size=1000,
            use_tbf=False
        )

        # Primary Trunk: s1 (Core) <---> s3 (Right Server/Lab B)
        self.addLink(
            s1, s3,
            port1=2, port2=1,
            bw=100,
            delay="1ms",
            loss=0,
            max_queue_size=1000,
            use_tbf=False
        )

        # FAILABLE LINK: s2 (Left) <---> s3 (Right)
        # Direct inter-switch trunk used for cross-lab traffic and primary failover testing
        self.addLink(
            s2, s3,
            port1=2, port2=2,
            bw=100,
            delay="2ms",
            loss=0,
            max_queue_size=1000,
            use_tbf=False
        )

        # -----------------------------------------------------------------
        # 4. Host & Server Links to Switches
        # -----------------------------------------------------------------
        # Hosts under s2 (ports 3 and 4)
        self.addLink(h1, s2, port1=0, port2=3, bw=100, delay="1ms")
        self.addLink(h2, s2, port1=0, port2=4, bw=100, delay="1ms")

        # Hosts under s3 (ports 3 and 4)
        self.addLink(h3, s3, port1=0, port2=3, bw=100, delay="1ms")
        self.addLink(h4, s3, port1=0, port2=4, bw=100, delay="1ms")

        # Server under s3 (port 5) — High bandwidth link (1Gbps)
        self.addLink(srv1, s3, port1=0, port2=5, bw=1000, delay="0.5ms")

        logger.info("SentinelNet University Topology built successfully.")


# Registration dictionary for Mininet CLI (`mn --custom topology.py --topo university`)
topos = {"university": (lambda: UniversityTopology())}


def run_network(
    test_mode: bool = False,
    controller_ip: str = "127.0.0.1",
    controller_port: int = 6633,
    debug: bool = False
) -> None:
    """Instantiate and run the Mininet simulation network.

    Args:
        test_mode: If True, executes automated connectivity tests (pingall & iperf) and exits.
        controller_ip: IP address of the remote Ryu SDN controller.
        controller_port: OpenFlow port of the Ryu controller (default: 6633 or 6653).
        debug: Enable verbose Mininet logging.
    """
    if Mininet is None:
        logger.error("Mininet is not installed or not supported on this platform. Please run on Linux.")
        sys.exit(1)

    setLogLevel("debug" if debug else "info")
    logger.info("Initializing Mininet with RemoteController at %s:%d...", controller_ip, controller_port)

    topo = UniversityTopology()
    controller = RemoteController("c0", ip=controller_ip, port=controller_port)

    net = Mininet(
        topo=topo,
        controller=controller,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=False,
        autoStaticArp=False
    )

    try:
        net.start()
        logger.info("=================================================================")
        logger.info("   SentinelNet AI Self-Healing Network Simulation Running")
        logger.info("=================================================================")
        logger.info("Switches: s1 (Core: 10.0.0.1), s2 (Left: 10.0.0.2), s3 (Right: 10.0.0.3)")
        logger.info("Hosts:    h1 (10.0.1.1), h2 (10.0.1.2), h3 (10.0.1.3), h4 (10.0.1.4)")
        logger.info("Server:   srv1 (10.0.0.50)")
        logger.info("Failable: s2 <---> s3 link (port 2 on both switches)")
        logger.info("=================================================================")

        if test_mode:
            logger.info("--- TEST MODE: Running automated connectivity verification ---")
            logger.info("Waiting 3s for OpenFlow flow tables to settle...")
            import time
            time.sleep(3)

            # Test 1: Full mesh pingall
            logger.info("Step 1/2: Testing full mesh reachability (pingall)...")
            loss = net.pingAll()
            logger.info("PingAll completed with %.2f%% packet loss", loss)

            # Test 2: Bandwidth throughput test between h1 (Client) and srv1 (Server)
            logger.info("Step 2/2: Measuring TCP throughput (h1 <---> srv1)...")
            h1 = net.get("h1")
            srv1 = net.get("srv1")
            iperf_result = net.iperf((h1, srv1))
            logger.info("iperf TCP result: %s", iperf_result)

            if loss == 0.0:
                logger.info(">>> VERIFICATION SUCCESSFUL: Network is fully operational. <<<")
            else:
                logger.warning(">>> VERIFICATION WARNING: Packet loss detected (%.2f%%). Check controller rules.", loss)
        else:
            logger.info("Entering Mininet Interactive CLI. Type 'exit' to shut down.")
            CLI(net)

    except Exception as exc:
        logger.critical("Error during Mininet execution: %s", str(exc), exc_info=True)
    finally:
        logger.info("Stopping Mininet network and cleaning up OpenFlow switch interfaces...")
        net.stop()
        logger.info("Mininet network stopped cleanly.")


def main():
    """Command-line interface entry point."""
    parser = argparse.ArgumentParser(
        description="SentinelNet Mininet University Network Topology Runner"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run automated pingall and iperf throughput tests, then exit."
    )
    parser.add_argument(
        "--controller-ip",
        default="127.0.0.1",
        help="IP address of the remote Ryu SDN controller (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--controller-port",
        type=int,
        default=6633,
        help="OpenFlow port of the remote Ryu controller (default: 6633)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debugging logs"
    )

    args = parser.parse_args()
    run_network(
        test_mode=args.test,
        controller_ip=args.controller_ip,
        controller_port=args.controller_port,
        debug=args.debug
    )


if __name__ == "__main__":
    main()
