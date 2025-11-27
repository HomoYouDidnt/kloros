#!/usr/bin/env python3
"""
TOON Capability Snapshot Demo

Demonstrates TOON compression on structured system state (capability registry).
Expected compression: 45-55% on uniform structured data.
"""

import sys
import json
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cognition.mind.memory.toon_state_export import export_state_toon, create_compact_snapshot


def load_capabilities_registry() -> dict:
    """Load full capabilities.yaml registry."""
    capabilities_path = Path("/home/kloros/src/registry/capabilities.yaml")

    if not capabilities_path.exists():
        print(f"ERROR: {capabilities_path} not found")
        sys.exit(1)

    with open(capabilities_path, 'r') as f:
        return yaml.safe_load(f)


def demonstrate_toon_snapshot():
    """Demonstrate TOON compression on capability registry."""
    print("=== TOON Capability Snapshot Demo ===\n")

    # Load full registry
    print("Loading capability registry...")
    capabilities = load_capabilities_registry()

    # Convert to JSON to measure original size
    json_str = json.dumps(capabilities, indent=2)
    json_bytes = len(json_str.encode('utf-8'))

    print(f"Registry loaded: {len(capabilities)} top-level entries")
    print(f"JSON size: {json_bytes:,} bytes ({json_bytes / 1024:.1f} KB)\n")

    # Export with TOON compression
    output_path = Path("/tmp/capability_snapshot.json")
    print("Exporting with TOON compression...")

    metrics = export_state_toon(
        state_data=capabilities,
        output_path=output_path,
        use_toon=True,
        include_json=True
    )

    print(f"\n=== Compression Results ===")
    print(f"Original (JSON):  {metrics['json_bytes']:,} bytes")
    print(f"TOON compressed:  {metrics['toon_bytes']:,} bytes")
    print(f"Savings:          {metrics['savings_pct']}%")
    print(f"\n=== Context Window Impact ===")

    # Estimate token counts (rough: 1 byte ≈ 0.3 tokens for structured data)
    json_tokens = int(json_bytes * 0.3)
    toon_tokens = int(metrics['toon_bytes'] * 0.3)

    print(f"JSON format:  ~{json_tokens:,} tokens")
    print(f"TOON format:  ~{toon_tokens:,} tokens")
    print(f"Tokens saved: ~{json_tokens - toon_tokens:,} tokens")

    multiplier = 100 / (100 - metrics['savings_pct']) if metrics['savings_pct'] > 0 else 1.0
    print(f"\nAnalysis multiplier: {multiplier:.2f}x more capability data in same context")

    # Show sample of TOON output
    print(f"\n=== Sample TOON Output ===")
    with open(output_path, 'r') as f:
        snapshot = json.load(f)

    if 'state_toon' in snapshot:
        toon_sample = snapshot['state_toon'][:500]
        print(f"{toon_sample}...")
        print(f"\n[Full TOON output: {len(snapshot['state_toon'])} chars]")

    print(f"\n=== Architectural Benefits ===")
    print("✓ System boundaries explicit (module dependencies visible)")
    print("✓ Capability contracts analyzable (enabled/disabled states)")
    print("✓ Full registry fits in LLM context (no truncation)")
    print("✓ Can trace coupling through TOON message schemas")

    print(f"\nSnapshot saved to: {output_path}")

    # Create compact snapshot for comparison
    print(f"\n=== Compact Snapshot (for LLM analysis) ===")
    compact = create_compact_snapshot(capabilities, max_depth=3, array_limit=5)
    compact_str = json.dumps(compact, indent=2)
    print(f"Compact snapshot: {len(compact_str)} bytes (truncated arrays/depth)")


if __name__ == "__main__":
    demonstrate_toon_snapshot()
