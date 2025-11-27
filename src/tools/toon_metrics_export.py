#!/usr/bin/env python3
"""
TOON Metrics Export Utility

Export KLoROS performance metrics in TOON format for analysis.
Metrics snapshots are time-series data (expected 40-50% compression).
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cognition.mind.memory.metrics import get_metrics
from src.cognition.mind.memory.toon_state_export import export_state_toon


def export_metrics_snapshot():
    """Export current metrics state with TOON compression."""
    print("=== Metrics Export with TOON ===\n")

    # Get current metrics
    metrics = get_metrics()
    metrics_data = metrics.get_stats()

    if not metrics_data:
        print("No metrics data available yet")
        return

    print(f"Operations tracked: {len(metrics_data)}")
    
    # Add metadata
    snapshot_data = {
        "timestamp": datetime.now().isoformat(),
        "metrics": metrics_data
    }

    # Export with TOON
    output_path = Path("/tmp/metrics_snapshot.json")
    
    compression_stats = export_state_toon(
        state_data=snapshot_data,
        output_path=output_path,
        use_toon=True,
        include_json=True
    )

    print(f"\n=== Compression Results ===")
    print(f"JSON format:  {compression_stats['json_bytes']:,} bytes")
    print(f"TOON format:  {compression_stats['toon_bytes']:,} bytes")
    print(f"Savings:      {compression_stats['savings_pct']}%")

    # Token estimates
    json_tokens = int(compression_stats['json_bytes'] * 0.3)
    toon_tokens = int(compression_stats['toon_bytes'] * 0.3)

    print(f"\n=== Context Window Impact ===")
    print(f"JSON format:  ~{json_tokens:,} tokens")
    print(f"TOON format:  ~{toon_tokens:,} tokens")

    multiplier = 100 / (100 - compression_stats['savings_pct']) if compression_stats['savings_pct'] > 0 else 1.0
    print(f"Multiplier:   {multiplier:.2f}x more metrics in same context")

    print(f"\n=== Use Cases ===")
    print("✓ Performance analysis across operations")
    print("✓ Latency trend tracking (p50/p95/p99)")
    print("✓ Operation throughput monitoring")
    print("✓ Bottleneck identification")

    print(f"\nSnapshot saved to: {output_path}")


if __name__ == "__main__":
    export_metrics_snapshot()
