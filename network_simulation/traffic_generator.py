"""Realistic Network Traffic Generator for SentinelNet.

Spawns and manages synthetic traffic flows using `iperf3`:
- Baseline constant traffic across campus hosts
- High-bandwidth stress flows (constant bit-rate)
- Dynamic bursty traffic patterns (simulating flash crowds/file transfers)
- Automated subprocess process lifecycle and file logging.
"""

import subprocess
import sys
import os
import time
import threading
import logging
import signal
from typing import Dict, Any, List, Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinelnet.traffic_generator")


class TrafficGenerator:
    """Manages synthetic background and test traffic generation via iperf3."""

    def __init__(self, log_dir: str = "logs/traffic"):
        """Initialize TrafficGenerator.

        Args:
            log_dir: Directory where iperf3 stdout/stderr logs will be saved.
        """
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self._processes: List[subprocess.Popen] = []
        self._threads: List[threading.Thread] = []
        self._stop_event = threading.Event()
        logger.info("TrafficGenerator initialized (logs: %s)", self.log_dir)

    def start_iperf_server(self, host_ip: str = "10.0.0.50", port: int = 5201) -> bool:
        """Start a background iperf3 daemon server on the target server.

        Args:
            host_ip: Destination server IP (default: srv1 at 10.0.0.50).
            port: Port for the iperf3 server daemon.

        Returns:
            bool: True if server launched successfully.
        """
        logger.info("Starting iperf3 server on port %d...", port)
        log_file = os.path.join(self.log_dir, f"server_{port}.log")
        try:
            with open(log_file, "a") as f_out:
                proc = subprocess.Popen(
                    ["iperf3", "-s", "-p", str(port)],
                    stdout=f_out,
                    stderr=subprocess.STDOUT
                )
            self._processes.append(proc)
            logger.info("iperf3 server running (PID: %d, Port: %d)", proc.pid, port)
            return True
        except FileNotFoundError:
            logger.warning("iperf3 binary not found on local path. Ensure iperf3 is installed.")
            return False

    def start_constant_traffic(
        self,
        src_ip: str,
        dst_ip: str = "10.0.0.50",
        mbps: float = 20.0,
        duration_sec: int = 60,
        port: int = 5201
    ) -> Optional[subprocess.Popen]:
        """Launch a constant bit-rate TCP/UDP iperf3 traffic stream.

        Args:
            src_ip: Source host identifier/IP.
            dst_ip: Target destination IP (default srv1: 10.0.0.50).
            mbps: Target throughput rate in Megabits per second.
            duration_sec: Stream duration in seconds.
            port: Target iperf3 server port.

        Returns:
            subprocess.Popen: Spawned process handle or None on failure.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(self.log_dir, f"traffic_const_{src_ip}_{dst_ip}_{timestamp}.log")
        logger.info("Launching constant traffic: %s -> %s (%.1f Mbps for %ds)",
                    src_ip, dst_ip, mbps, duration_sec)

        cmd = [
            "iperf3",
            "-c", dst_ip,
            "-p", str(port),
            "-b", f"{mbps}M",
            "-t", str(duration_sec),
            "--interval", "2"
        ]

        try:
            with open(log_file, "w") as f_out:
                proc = subprocess.Popen(cmd, stdout=f_out, stderr=subprocess.STDOUT)
            self._processes.append(proc)
            logger.info("Constant traffic stream started (PID: %d)", proc.pid)
            return proc
        except Exception as e:
            logger.error("Failed to launch iperf3 constant traffic: %s", str(e))
            return None

    def start_bursty_traffic(
        self,
        src_ip: str,
        dst_ip: str = "10.0.0.50",
        high_mbps: float = 85.0,
        low_mbps: float = 5.0,
        burst_interval_sec: int = 10,
        total_duration_sec: int = 120,
        port: int = 5201
    ) -> None:
        """Generate alternating high-burst and low-baseline traffic pattern in background.

        Args:
            src_ip: Source host IP.
            dst_ip: Destination server IP.
            high_mbps: High burst bandwidth (causes congestion).
            low_mbps: Normal low baseline bandwidth.
            burst_interval_sec: Duration of each phase in seconds.
            total_duration_sec: Overall run time.
            port: Target server port.
        """
        def _burst_worker():
            logger.info("Starting bursty traffic generator worker (%s -> %s)...", src_ip, dst_ip)
            start_time = time.time()
            is_high = False

            while not self._stop_event.is_set():
                elapsed = time.time() - start_time
                if elapsed >= total_duration_sec:
                    break

                current_rate = high_mbps if is_high else low_mbps
                phase_label = "HIGH BURST" if is_high else "LOW BASELINE"
                logger.info("[%s] Sending %.1f Mbps for %ds from %s",
                            phase_label, current_rate, burst_interval_sec, src_ip)

                proc = self.start_constant_traffic(
                    src_ip=src_ip,
                    dst_ip=dst_ip,
                    mbps=current_rate,
                    duration_sec=burst_interval_sec,
                    port=port
                )
                if proc:
                    proc.wait()

                is_high = not is_high

            logger.info("Bursty traffic generation finished for %s.", src_ip)

        t = threading.Thread(target=_burst_worker, daemon=True)
        t.start()
        self._threads.append(t)

    def start_baseline_traffic(self, target_server: str = "10.0.0.50") -> None:
        """Start steady multi-host baseline background traffic across campus network.

        Simulates ordinary student web browsing and database access from all 4 lab hosts.

        Args:
            target_server: Server IP receiving the baseline queries.
        """
        logger.info("Starting baseline campus network traffic from hosts h1-h4...")
        clients = ["10.0.1.1", "10.0.1.2", "10.0.1.3", "10.0.1.4"]

        for idx, client_ip in enumerate(clients):
            # Staggered steady 2-5 Mbps traffic streams
            self.start_constant_traffic(
                src_ip=client_ip,
                dst_ip=target_server,
                mbps=3.0,
                duration_sec=300,
                port=5201
            )
            time.sleep(0.5)

        logger.info(">>> BASELINE TRAFFIC ACTIVE: 4 client streams running <<<")

    def stop_all(self) -> None:
        """Terminate all active iperf3 processes and background threads."""
        logger.info("Stopping all traffic generation streams...")
        self._stop_event.set()

        for proc in self._processes:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()

        self._processes.clear()
        logger.info(">>> ALL TRAFFIC STREAMS STOPPED CLEANLY <<<")


# -----------------------------------------------------------------------------
# CLI Entry Point
# -----------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="SentinelNet Synthetic Traffic Generator")
    parser.add_argument("--server", action="store_true", help="Start background iperf3 server daemon on 10.0.0.50")
    parser.add_argument("--baseline", action="store_true", help="Start steady baseline traffic from all lab hosts")
    parser.add_argument("--constant", action="store_true", help="Start single constant-rate traffic stream")
    parser.add_argument("--bursty", action="store_true", help="Start alternating bursty traffic stream")
    parser.add_argument("--src", default="10.0.1.1", help="Source IP (default: 10.0.1.1)")
    parser.add_argument("--dst", default="10.0.0.50", help="Destination server IP (default: 10.0.0.50)")
    parser.add_argument("--rate", type=float, default=25.0, help="Throughput rate in Mbps (default: 25.0)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds (default: 60)")

    args = parser.parse_args()
    generator = TrafficGenerator()

    if args.server:
        generator.start_iperf_server()
        print("iperf3 server running in background. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            generator.stop_all()

    elif args.baseline:
        generator.start_baseline_traffic(target_server=args.dst)
        print("Baseline traffic running. Press Ctrl+C to terminate.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            generator.stop_all()

    elif args.bursty:
        generator.start_bursty_traffic(src_ip=args.src, dst_ip=args.dst, high_mbps=args.rate, total_duration_sec=args.duration)
        print(f"Bursty traffic active for {args.duration}s. Press Ctrl+C to stop.")
        try:
            time.sleep(args.duration)
        except KeyboardInterrupt:
            generator.stop_all()

    elif args.constant:
        proc = generator.start_constant_traffic(src_ip=args.src, dst_ip=args.dst, mbps=args.rate, duration_sec=args.duration)
        if proc:
            proc.wait()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
