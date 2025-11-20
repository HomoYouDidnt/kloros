"""
ToolGen Harness: CLI for standalone tool generation and evaluation.

Usage:
    python -m toolgen.harness --spec specs/text_deduplicate.json --out /tmp/bundle
"""
from __future__ import annotations
import argparse
import pathlib
import json
import sys

from toolgen.evaluator import ToolGenEvaluator

def main():
    """CLI entry point."""
    ap = argparse.ArgumentParser(
        description="Generate and evaluate tools from specifications"
    )
    ap.add_argument("--spec", required=True, help="Path to tool spec JSON")
    ap.add_argument("--out", required=True, help="Output directory for bundle")
    ap.add_argument("--epoch", type=int, default=0, help="Epoch number for annealing (default: 0)")
    ap.add_argument("--impl_style", default="set", help="Implementation style (set/trie/lsh/suffixarray)")
    args = ap.parse_args()

    spec_path = pathlib.Path(args.spec)
    output_dir = pathlib.Path(args.out)

    if not spec_path.exists():
        print(f"Error: Spec file not found: {spec_path}", file=sys.stderr)
        return 1

    # Create evaluator and run
    evaluator = ToolGenEvaluator()
    print(f"Synthesizing tool from {spec_path}...")
    print(f"Epoch: {args.epoch}, Impl Style: {args.impl_style}")

    try:
        result = evaluator.evaluate(spec_path, output_dir, epoch=args.epoch, impl_style=args.impl_style)
        
        print("\n" + "=" * 60)
        print("ToolGen Evaluation Results")
        print("=" * 60)
        print(f"Tool ID: {result['tool_id']}")
        print(f"Bundle Path: {result['bundle_path']}")
        print(f"\nOverall Fitness: {result['fitness']:.3f}")

        if 'budgets' in result:
            print(f"\nAnnealed Budgets (Epoch {result.get('epoch', 0)}):")
            print(f"  Timeout  : {result['budgets'].get('time_ms', 'N/A')}ms")
            print(f"  Memory   : {result['budgets'].get('mem_mb', 'N/A')}MB")

        print("\nComponent Scores:")
        for comp, score in result['components'].items():
            if comp == "stability" and score < 1.0:
                print(f"  {comp:15s}: {score:.3f} ⚠️  FLAKY!")
            else:
                print(f"  {comp:15s}: {score:.3f}")

        if result.get('impl_style'):
            print(f"\nImplementation Style: {result['impl_style']}")

        if result['violations']:
            print("\nSafety Violations:")
            for v in result['violations']:
                print(f"  - {v}")

        if result.get('median_ms'):
            print(f"\nPerformance Telemetry:")
            print(f"  Median Latency: {result['median_ms']:.2f}ms")
            print(f"  Budget       : {result['budgets'].get('time_ms', 'N/A')}ms")

        if result.get('repair_strategy'):
            print(f"\nRepair Agent (Phase 6):")
            print(f"  Strategy : {result['repair_strategy']}")
            print(f"  Pattern  : {result.get('repair_pattern_id', 'N/A')}")
            print(f"  Attempts : {result.get('repair_attempts', 'N/A')}")

        if result.get('handoff'):
            print(f"\nCross-Domain Handoff:")
            print(f"  → RepairLab queue: {result['handoff']}")

        print("\nTest Output:")
        print(result['test_output'])
        print("=" * 60)
        
        return 0 if result['fitness'] > 0.8 else 1
        
    except Exception as e:
        print(f"Error during evaluation: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
