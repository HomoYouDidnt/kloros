#!/usr/bin/env python3
"""
TOON Question Queue Demo

Demonstrates TOON compression on curiosity question queues.
Expected compression: 35-45% on uniform question records.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cognition.mind.memory.toon_question_utils import export_question_queue_snapshot


def demonstrate_question_queue_compression():
    """Demonstrate TOON compression on processed questions."""
    print("=== TOON Question Queue Demo ===\n")

    processed_questions_path = Path("/home/kloros/.kloros/processed_questions.jsonl")
    
    if not processed_questions_path.exists():
        print(f"ERROR: {processed_questions_path} not found")
        sys.exit(1)

    print(f"Source: {processed_questions_path}")
    print(f"Size: {processed_questions_path.stat().st_size / 1024:.1f} KB\n")

    # Export snapshot with TOON compression (sample 500 records)
    print("Exporting sample (500 records) with TOON compression...")
    
    output_path = Path("/tmp/question_queue_snapshot.json")
    metrics = export_question_queue_snapshot(
        input_path=processed_questions_path,
        output_path=output_path,
        limit=500,
        use_toon=True
    )

    print(f"\n=== Compression Results ===")
    print(f"Records analyzed: {metrics['record_count']}")
    print(f"JSON format:      {metrics['json_bytes']:,} bytes")
    print(f"TOON format:      {metrics['toon_bytes']:,} bytes")
    print(f"Savings:          {metrics['savings_pct']}%")

    # Token estimates
    json_tokens = int(metrics['json_bytes'] * 0.3)
    toon_tokens = int(metrics['toon_bytes'] * 0.3)

    print(f"\n=== Context Window Impact ===")
    print(f"JSON format:  ~{json_tokens:,} tokens")
    print(f"TOON format:  ~{toon_tokens:,} tokens")
    print(f"Tokens saved: ~{json_tokens - toon_tokens:,} tokens")

    multiplier = 100 / (100 - metrics['savings_pct']) if metrics['savings_pct'] > 0 else 1.0
    print(f"\nAnalysis multiplier: {multiplier:.2f}x more question data in same context")

    # Show TOON sample
    print(f"\n=== Sample TOON Output ===")
    import json
    with open(output_path, 'r') as f:
        snapshot = json.load(f)

    if 'questions_toon' in snapshot:
        toon_sample = snapshot['questions_toon'][:600]
        print(toon_sample + "...")
        print(f"\n[Full TOON output: {len(snapshot['questions_toon'])} chars]")

    print(f"\n=== Architectural Benefits ===")
    print("✓ Question deduplication visible (evidence_hash)")
    print("✓ Processing history analyzable (processed_at timestamps)")
    print("✓ Intent tracking clear (intent_sha evolution)")
    print("✓ Can load entire question queue in context")

    print(f"\nSnapshot saved to: {output_path}")


if __name__ == "__main__":
    demonstrate_question_queue_compression()
