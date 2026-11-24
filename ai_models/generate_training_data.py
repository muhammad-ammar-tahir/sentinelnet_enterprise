"""Synthetic Telemetry Generator for SentinelNet.

Generates 10,000 realistic network telemetry records across campus switches/hosts
sampled at 5-second intervals (~13.8 hours).
Injects realistic multi-modal network anomalies (5% contamination):
- Latency spikes
- Packet loss bursts
- CPU saturations
- Interface down drops
- High interface CRC/packet error counter deltas
Saves output to `ai_models/data/training_data.csv`.
"""

import os
import random
import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sentinelnet.generate_data")


def generate_synthetic_telemetry(
    num_rows: int = 10000,
    anomaly_ratio: float = 0.05,
    output_path: str = "ai_models/data/training_data.csv",
    seed: int = 42
) -> pd.DataFrame:
    """Generate synthetic time-series network telemetry dataset.

    Args:
        num_rows: Total rows to generate (default: 10,000).
        anomaly_ratio: Percentage of injected anomalies (default: 0.05 = 5%).
        output_path: Path to destination CSV file.
        seed: Random seed for reproducibility.

    Returns:
        pd.DataFrame containing generated telemetry.
    """
    logger.info("Generating %d synthetic network telemetry records (seed=%d)...", num_rows, seed)
    np.random.seed(seed)
    random.seed(seed)

    devices = ["s1", "s2", "s3", "h1", "h2", "h3", "h4", "srv1"]
    start_time = datetime(2026, 11, 20, 8, 0, 0)

    timestamps = [start_time + timedelta(seconds=5 * i) for i in range(num_rows)]
    num_anomalies = int(num_rows * anomaly_ratio)
    anomaly_indices = set(np.random.choice(num_rows, size=num_anomalies, replace=False))

    records = []

    for i in range(num_rows):
        ts = timestamps[i].isoformat()
        dev = devices[i % len(devices)]
        is_anomaly = 1 if i in anomaly_indices else 0

        if not is_anomaly:
            # Baseline normal campus network operation
            latency_ms = float(np.random.normal(loc=12.0, scale=4.0))
            latency_ms = float(np.clip(latency_ms, 5.0, 30.0))

            packet_loss_pct = float(np.random.exponential(scale=0.05))
            packet_loss_pct = float(np.clip(packet_loss_pct, 0.0, 0.5))

            cpu_pct = float(np.random.normal(loc=35.0, scale=8.0))
            cpu_pct = float(np.clip(cpu_pct, 15.0, 60.0))

            memory_pct = float(np.random.normal(loc=40.0, scale=5.0))
            memory_pct = float(np.clip(memory_pct, 25.0, 55.0))

            bandwidth_mbps = float(np.random.normal(loc=45.0, scale=10.0))
            bandwidth_mbps = float(np.clip(bandwidth_mbps, 20.0, 75.0))

            interface_up = 1
            error_count = int(np.random.poisson(lam=0.2))

        else:
            # Multi-pattern failure anomaly injection
            anomaly_type = random.choice([
                "LATENCY_SPIKE",
                "PACKET_LOSS_BURST",
                "CPU_SATURATION",
                "INTERFACE_DROP",
                "CONGESTION_SATURATION"
            ])

            if anomaly_type == "LATENCY_SPIKE":
                latency_ms = float(np.random.uniform(90.0, 350.0))
                packet_loss_pct = float(np.random.uniform(1.0, 4.0))
                cpu_pct = float(np.random.uniform(40.0, 70.0))
                memory_pct = float(np.random.uniform(40.0, 60.0))
                bandwidth_mbps = float(np.random.uniform(30.0, 60.0))
                interface_up = 1
                error_count = int(np.random.randint(5, 25))

            elif anomaly_type == "PACKET_LOSS_BURST":
                latency_ms = float(np.random.uniform(35.0, 95.0))
                packet_loss_pct = float(np.random.uniform(8.0, 35.0))
                cpu_pct = float(np.random.uniform(45.0, 75.0))
                memory_pct = float(np.random.uniform(40.0, 65.0))
                bandwidth_mbps = float(np.random.uniform(10.0, 40.0))
                interface_up = 1
                error_count = int(np.random.randint(30, 150))

            elif anomaly_type == "CPU_SATURATION":
                latency_ms = float(np.random.uniform(50.0, 140.0))
                packet_loss_pct = float(np.random.uniform(3.0, 12.0))
                cpu_pct = float(np.random.uniform(88.0, 99.5))
                memory_pct = float(np.random.uniform(75.0, 95.0))
                bandwidth_mbps = float(np.random.uniform(60.0, 90.0))
                interface_up = 1
                error_count = int(np.random.randint(10, 40))

            elif anomaly_type == "INTERFACE_DROP":
                latency_ms = 999.0  # Timeout
                packet_loss_pct = 100.0  # Total loss
                cpu_pct = float(np.random.uniform(20.0, 40.0))
                memory_pct = float(np.random.uniform(30.0, 50.0))
                bandwidth_mbps = 0.0
                interface_up = 0
                error_count = int(np.random.randint(100, 500))

            else:  # CONGESTION_SATURATION
                latency_ms = float(np.random.uniform(70.0, 180.0))
                packet_loss_pct = float(np.random.uniform(4.0, 15.0))
                cpu_pct = float(np.random.uniform(70.0, 88.0))
                memory_pct = float(np.random.uniform(60.0, 80.0))
                bandwidth_mbps = float(np.random.uniform(92.0, 99.8))
                interface_up = 1
                error_count = int(np.random.randint(20, 80))

        records.append({
            "timestamp": ts,
            "device_id": dev,
            "latency_ms": round(latency_ms, 2),
            "packet_loss_pct": round(packet_loss_pct, 2),
            "cpu_pct": round(cpu_pct, 2),
            "memory_pct": round(memory_pct, 2),
            "bandwidth_mbps": round(bandwidth_mbps, 2),
            "interface_up": int(interface_up),
            "error_count": int(error_count),
            "is_anomaly": is_anomaly
        })

    df = pd.DataFrame(records)

    # Save to directory
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)

    anomaly_cnt = df["is_anomaly"].sum()
    logger.info("Successfully generated %d rows with %d anomalies (%.2f%%) to '%s'",
                len(df), anomaly_cnt, (anomaly_cnt / len(df)) * 100.0, output_path)

    return df


if __name__ == "__main__":
    generate_synthetic_telemetry()
