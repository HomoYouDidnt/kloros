#!/usr/bin/env python3
"""
ToolGen Performance Chart: Plot median latency vs epoch across specs.

Usage:
    python /home/kloros/bin/plot_toolgen_perf.py
"""
import csv
import collections
import pathlib

try:
    import matplotlib.pyplot as plt
except ImportError:
    print("ERROR: matplotlib not installed. Install with: pip install matplotlib")
    import sys
    sys.exit(1)

CSV_FILE = pathlib.Path("/tmp/toolgen_perf.csv")
OUTPUT_PNG = pathlib.Path("/tmp/toolgen_perf.png")


def main():
    """Generate performance chart from CSV data."""
    if not CSV_FILE.exists():
        print(f"ERROR: CSV file not found: {CSV_FILE}")
        print("Generate it first with:")
        print('  grep \'"domain":"toolgen"\' /home/kloros/logs/dream/metrics.jsonl | \\')
        print('  jq -r \'[.epoch, .median_ms, .spec_path | split("/")[-1]] | @csv\' > /tmp/toolgen_perf.csv')
        return 1

    # Parse CSV and group by spec
    rows = list(csv.reader(open(CSV_FILE)))
    by_spec = collections.defaultdict(lambda: ([], []))

    for row in rows:
        if len(row) < 3:
            continue
        try:
            epoch = int(float(row[0]))
            median_ms = float(row[1])
            spec = row[2].strip('"')  # Remove quotes if present
            by_spec[spec][0].append(epoch)
            by_spec[spec][1].append(median_ms)
        except (ValueError, IndexError):
            continue

    if not by_spec:
        print("ERROR: No valid data found in CSV")
        return 1

    # Plot
    plt.figure(figsize=(10, 6))
    for spec, (xs, ys) in sorted(by_spec.items()):
        plt.plot(xs, ys, marker="o", label=spec, linewidth=2, markersize=6)

    plt.xlabel("Epoch", fontsize=12)
    plt.ylabel("Median Latency (ms)", fontsize=12)
    plt.title("ToolGen Performance Evolution", fontsize=14, fontweight="bold")
    plt.legend(loc="best")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    plt.savefig(OUTPUT_PNG, dpi=150)
    print(f"✓ Chart saved: {OUTPUT_PNG}")
    print(f"  Data points: {sum(len(xs) for xs, _ in by_spec.values())}")
    print(f"  Specs: {', '.join(by_spec.keys())}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
