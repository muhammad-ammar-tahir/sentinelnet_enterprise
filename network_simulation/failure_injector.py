"""Network Failure Injection Harness for SentinelNet.

Provides the `FailureInjector` class and CLI menu to simulate live network anomalies:
- Link failures (bringing down interfaces or OpenFlow ports)
- Device failures (terminating/disabling switches)
- Latency degradation via Linux `tc netem`
- Packet loss injection via Linux `tc netem`
- Bandwidth throttling / Congestion injection via Linux `tc tbf`
- Comprehensive state tracking and atomic cleanup/restoration.
"""

import subprocess
import sys
import os
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinelnet.failure_injector")


class FailureInjector:
    """Manages active network failure injections on Mininet OVS switches and interfaces."""

    def __init__(self, net=None):
        """Initialize FailureInjector.

        Args:
            net: Optional Mininet network instance if running directly within a Mininet script.
        """
        self.net = net
        self.active_failures: Dict[str, Dict[str, Any]] = {}
        logger.info("FailureInjector initialized (Mininet net instance: %s)", "Attached" if net else "Standalone CLI mode")

    # -------------------------------------------------------------------------
    # Shell Execution Helpers
    # -------------------------------------------------------------------------
    def _run_cmd(self, cmd: List[str]) -> bool:
        """Run a shell command safely, logging output and checking return code."""
        cmd_str = " ".join(cmd)
        logger.debug("Executing shell command: %s", cmd_str)
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if result.returncode != 0:
                logger.warning("Command returned code %d: %s (stderr: %s)",
                               result.returncode, cmd_str, result.stderr.strip())
                return False
            return True
        except Exception as e:
            logger.error("Failed to execute command '%s': %s", cmd_str, str(e))
            return False

    def _get_interface_for_link(self, sw1: str, sw2: str) -> Optional[str]:
        """Resolve interface name connecting sw1 and sw2 (e.g., s2-eth2 <-> s3-eth2)."""
        # Standard Mininet naming convention for UniversityTopology:
        # s1-eth1 <-> s2-eth1
        # s1-eth2 <-> s3-eth1
        # s2-eth2 <-> s3-eth2 (failable link)
        pair = {sw1.lower(), sw2.lower()}
        if pair == {"s2", "s3"}:
            return f"{sw1}-eth2"
        elif pair == {"s1", "s2"}:
            return f"{sw1}-eth1"
        elif pair == {"s1", "s3"}:
            return f"{sw1}-eth2" if sw1 == "s1" else f"{sw1}-eth1"
        return f"{sw1}-eth1"

    # -------------------------------------------------------------------------
    # Core Injection Methods
    # -------------------------------------------------------------------------
    def kill_link(self, sw1: str, sw2: str) -> bool:
        """Bring down the physical/virtual link connecting switch sw1 and switch sw2.

        Uses Mininet `configLinkStatus` if available, or drops the OpenFlow port / ip link.

        Args:
            sw1: First switch name (e.g. 's2').
            sw2: Second switch name (e.g. 's3').

        Returns:
            bool: True if link was brought down.
        """
        link_id = f"link_{sw1}_{sw2}"
        logger.warning("Injecting LINK FAILURE on trunk: %s <---> %s", sw1, sw2)

        success = False
        if self.net:
            try:
                self.net.configLinkStatus(sw1, sw2, "down")
                success = True
            except Exception as e:
                logger.error("Mininet configLinkStatus failed: %s", str(e))

        if not success:
            intf1 = self._get_interface_for_link(sw1, sw2)
            intf2 = self._get_interface_for_link(sw2, sw1)
            # Bring down interfaces via ip link
            ok1 = self._run_cmd(["ip", "link", "set", "dev", intf1, "down"])
            ok2 = self._run_cmd(["ip", "link", "set", "dev", intf2, "down"])
            success = ok1 or ok2

        if success:
            self.active_failures[link_id] = {
                "type": "LINK_DOWN",
                "sw1": sw1,
                "sw2": sw2,
                "timestamp": datetime.utcnow().isoformat(),
                "description": f"Physical link between {sw1} and {sw2} brought down"
            }
            logger.info(">>> LINK FAILURE ACTIVE: %s <---> %s is DOWN <<<", sw1, sw2)
        return success

    def kill_device(self, switch_name: str) -> bool:
        """Simulate hardware/power failure by stopping or disabling an OpenFlow switch.

        Args:
            switch_name: Switch identifier (e.g. 's2').

        Returns:
            bool: True if switch was brought down.
        """
        logger.critical("Injecting DEVICE FAILURE on switch: %s", switch_name)
        dev_id = f"device_{switch_name}"

        success = False
        if self.net:
            try:
                sw = self.net.get(switch_name)
                sw.stop()
                success = True
            except Exception as e:
                logger.error("Mininet switch.stop() failed: %s", str(e))

        if not success:
            # Standalone fallback: disable loopback and bridge interface
            ok1 = self._run_cmd(["ovs-vsctl", "del-br", switch_name])
            ok2 = self._run_cmd(["ip", "link", "set", "dev", switch_name, "down"])
            success = ok1 or ok2

        if success:
            self.active_failures[dev_id] = {
                "type": "DEVICE_DOWN",
                "device": switch_name,
                "timestamp": datetime.utcnow().isoformat(),
                "description": f"OpenFlow switch {switch_name} has crashed / powered down"
            }
            logger.info(">>> DEVICE FAILURE ACTIVE: %s is DOWN <<<", switch_name)
        return success

    def inject_latency(self, target: str, ms: float) -> bool:
        """Inject artificial latency/delay on a target host or switch interface using tc netem.

        Args:
            target: Interface or node name (e.g. 's2-eth2' or 'h1').
            ms: Milliseconds of latency to add.

        Returns:
            bool: True if latency was configured.
        """
        intf = f"{target}-eth0" if not "-" in target else target
        logger.warning("Injecting %.1fms LATENCY on interface %s", ms, intf)

        # Clear existing qdisc if any, then add netem delay
        self._run_cmd(["tc", "qdisc", "del", "dev", intf, "root"])
        success = self._run_cmd(["tc", "qdisc", "add", "dev", intf, "root", "netem", "delay", f"{ms}ms"])

        if success:
            self.active_failures[f"latency_{intf}"] = {
                "type": "HIGH_LATENCY",
                "interface": intf,
                "delay_ms": ms,
                "timestamp": datetime.utcnow().isoformat()
            }
            logger.info(">>> LATENCY INJECTED: +%.1fms on %s <<<", ms, intf)
        return success

    def inject_packet_loss(self, target: str, pct: float) -> bool:
        """Inject artificial packet loss percentage on a target interface using tc netem.

        Args:
            target: Interface or node name (e.g. 's2-eth2' or 'h1').
            pct: Percentage of packet loss (0.0 to 100.0).

        Returns:
            bool: True if loss was configured.
        """
        intf = f"{target}-eth0" if not "-" in target else target
        logger.warning("Injecting %.1f%% PACKET LOSS on interface %s", pct, intf)

        self._run_cmd(["tc", "qdisc", "del", "dev", intf, "root"])
        success = self._run_cmd(["tc", "qdisc", "add", "dev", intf, "root", "netem", "loss", f"{pct}%"])

        if success:
            self.active_failures[f"loss_{intf}"] = {
                "type": "PACKET_LOSS",
                "interface": intf,
                "loss_pct": pct,
                "timestamp": datetime.utcnow().isoformat()
            }
            logger.info(">>> PACKET LOSS INJECTED: %.1f%% on %s <<<", pct, intf)
        return success

    def inject_congestion(self, link_or_intf: str, mbps: float) -> bool:
        """Throttle interface bandwidth using Token Bucket Filter (TBF) to cause severe congestion.

        Args:
            link_or_intf: Interface name (e.g. 's2-eth2').
            mbps: Bandwidth cap in Megabits per second (e.g. 1.0 or 0.5).

        Returns:
            bool: True if bandwidth throttling was applied.
        """
        intf = link_or_intf
        logger.warning("Injecting BANDWIDTH CONGESTION: Throttling %s to %.2f Mbps", intf, mbps)

        rate_kbit = int(mbps * 1000)
        self._run_cmd(["tc", "qdisc", "del", "dev", intf, "root"])
        # tbf configuration: rate, burst, latency
        success = self._run_cmd([
            "tc", "qdisc", "add", "dev", intf, "root", "tbf",
            "rate", f"{rate_kbit}kbit",
            "burst", "32kbit",
            "latency", "400ms"
        ])

        if success:
            self.active_failures[f"congestion_{intf}"] = {
                "type": "CONGESTION",
                "interface": intf,
                "rate_mbps": mbps,
                "timestamp": datetime.utcnow().isoformat()
            }
            logger.info(">>> CONGESTION INJECTED: %s throttled to %.2f Mbps <<<", intf, mbps)
        return success

    def restore_all(self) -> None:
        """Clean up and revert all active failures, restoring default link and queue states."""
        logger.info("Restoring all network links, interfaces, and queuing disciplines...")

        for fail_id, failure in list(self.active_failures.items()):
            ftype = failure.get("type")
            if ftype == "LINK_DOWN":
                sw1, sw2 = failure["sw1"], failure["sw2"]
                if self.net:
                    try:
                        self.net.configLinkStatus(sw1, sw2, "up")
                    except Exception:
                        pass
                intf1 = self._get_interface_for_link(sw1, sw2)
                intf2 = self._get_interface_for_link(sw2, sw1)
                self._run_cmd(["ip", "link", "set", "dev", intf1, "up"])
                self._run_cmd(["ip", "link", "set", "dev", intf2, "up"])
                logger.info("Restored link: %s <---> %s", sw1, sw2)

            elif ftype == "DEVICE_DOWN":
                dev = failure["device"]
                self._run_cmd(["ip", "link", "set", "dev", dev, "up"])
                if self.net:
                    try:
                        sw = self.net.get(dev)
                        sw.start([self.net.controller])
                    except Exception:
                        pass
                logger.info("Restored device: %s", dev)

            elif ftype in ("HIGH_LATENCY", "PACKET_LOSS", "CONGESTION"):
                intf = failure.get("interface")
                if intf:
                    self._run_cmd(["tc", "qdisc", "del", "dev", intf, "root"])
                    logger.info("Deleted tc qdisc on interface %s", intf)

        self.active_failures.clear()
        logger.info(">>> ALL NETWORK INJECTIONS RESTORED TO HEALTHY BASELINE <<<")

    def list_active_failures(self) -> List[Dict[str, Any]]:
        """Return a list of all currently active failure injections."""
        return list(self.active_failures.values())


# -----------------------------------------------------------------------------
# Interactive CLI Menu for Demonstrations
# -----------------------------------------------------------------------------
def run_interactive_cli():
    """Interactive command-line menu for live self-healing demonstrations."""
    injector = FailureInjector()

    MENU = """
===========================================================
  SentinelNet Network Failure Injection Console
===========================================================
  [1] Kill Link (s2 <---> s3) [Primary Failable Trunk]
  [2] Kill Device (Switch s2 or s3)
  [3] Inject Latency (+50ms delay on s2-eth2)
  [4] Inject Packet Loss (20% loss on s2-eth2)
  [5] Inject Bandwidth Congestion (Throttle to 1 Mbps)
  [6] List Active Injections
  [7] RESTORE ALL (Revert back to 100% healthy network)
  [0] Exit
===========================================================
"""

    while True:
        print(MENU)
        active = injector.list_active_failures()
        print(f"Active Failures: {len(active)}")
        for f in active:
            print(f"  * [{f.get('type')}] {f.get('description', f.get('interface'))}")
        print("-----------------------------------------------------------")

        try:
            choice = input("Select an option (0-7): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting and restoring network...")
            injector.restore_all()
            break

        if choice == "1":
            print("Bringing down trunk link between Switch s2 and Switch s3...")
            injector.kill_link("s2", "s3")

        elif choice == "2":
            target_sw = input("Enter switch name to terminate (s1/s2/s3) [default: s2]: ").strip() or "s2"
            injector.kill_device(target_sw)

        elif choice == "3":
            intf = input("Enter target interface [default: s2-eth2]: ").strip() or "s2-eth2"
            delay = input("Enter latency in ms [default: 50]: ").strip() or "50"
            injector.inject_latency(intf, float(delay))

        elif choice == "4":
            intf = input("Enter target interface [default: s2-eth2]: ").strip() or "s2-eth2"
            loss = input("Enter packet loss percent [default: 20]: ").strip() or "20"
            injector.inject_packet_loss(intf, float(loss))

        elif choice == "5":
            intf = input("Enter target interface [default: s2-eth2]: ").strip() or "s2-eth2"
            bw = input("Enter max bandwidth in Mbps [default: 1.0]: ").strip() or "1.0"
            injector.inject_congestion(intf, float(bw))

        elif choice == "6":
            print("\n--- Current Active Failure Injections ---")
            if not active:
                print("No failures active. Network is fully healthy.")
            for idx, item in enumerate(active, 1):
                print(f"{idx}. {item}")

        elif choice == "7":
            injector.restore_all()

        elif choice == "0":
            print("Cleaning up and exiting...")
            injector.restore_all()
            break

        else:
            print("Invalid selection. Please choose an option from 0 to 7.")

        time.sleep(1)


if __name__ == "__main__":
    run_interactive_cli()
