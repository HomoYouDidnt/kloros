#!/usr/bin/env python3
"""
TOON Investigation Analyzer - Demonstrate analysis scalability gains.

Shows how TOON compression enables examining 2-3x more investigation history
within LLM context limits.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cognition.mind.memory.toon_jsonl_utils import (
    read_jsonl_tail_toon,
    analyze_jsonl_size_savings
)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Analyze investigations with TOON compression')
    parser.add_argument('--tail', type=int, default=50,
                       help='Number of recent investigations to show (default: 50)')
    parser.add_argument('--analyze-savings', action='store_true',
                       help='Analyze potential compression savings')
    parser.add_argument('--use-json', action='store_true',
                       help='Output JSON instead of TOON')
    parser.add_argument('--sample-size', type=int, default=1000,
                       help='Sample size for savings analysis (default: 1000)')

    args = parser.parse_args()

    investigations_file = Path("/home/kloros/.kloros/curiosity_investigations.jsonl")

    if not investigations_file.exists():
        print(f"ERROR: {investigations_file} not found")
        sys.exit(1)

    if args.analyze_savings:
        print("=== Analyzing TOON Compression Savings ===\n")
        metrics = analyze_jsonl_size_savings(investigations_file, sample_size=args.sample_size)

        print(f"File: {metrics['file_path']}")
        print(f"Total Size: {metrics['file_size_mb']:.2f} MB")
        print(f"\nSample Analysis ({metrics['sample_count']} records):")
        print(f"  JSON:  {metrics['json_bytes']:,} bytes")
        print(f"  TOON:  {metrics['toon_bytes']:,} bytes")
        print(f"  Savings: {metrics['savings_pct']}%")
        print(f"\nProjected full file TOON size: {metrics['file_size_mb'] * (1 - metrics['savings_pct']/100):.2f} MB")
        print(f"\nContext Window Impact:")
        print(f"  With JSON: ~{int(metrics['file_size_mb'] * 4)} investigations in 200k tokens")
        print(f"  With TOON: ~{int(metrics['file_size_mb'] * 4 * (100/(100-metrics['savings_pct'])))} investigations in 200k tokens")
        print(f"  Multiplier: {100/(100-metrics['savings_pct']):.1f}x more analyzable data")

    else:
        print(f"=== Last {args.tail} Investigations ===\n")
        use_toon = not args.use_json

        output = read_jsonl_tail_toon(
            investigations_file,
            n_records=args.tail,
            use_toon=use_toon
        )

        format_name = "TOON" if use_toon else "JSON"
        print(f"Format: {format_name}")
        print(f"Size: {len(output):,} bytes\n")
        print(output)


if __name__ == "__main__":
    main()
