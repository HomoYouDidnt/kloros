#!/usr/bin/env python3
"""Test config tuning runner."""

import sys
import json
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, '/home/kloros')

# Set environment for self-healing
os.environ['KLR_SELF_HEALING_MODE'] = 'dev'

from src.dream.config_tuning import ConfigTuningRunner

def main():
    print("=" * 60)
    print("Testing Config Tuning Runner")
    print("=" * 60)

    # Load test intent
    intent_file = Path("/home/kloros/.kloros/intents/test_vllm_oom_1761758875.json")

    if not intent_file.exists():
        print(f"❌ Intent file not found: {intent_file}")
        return 1

    with open(intent_file) as f:
        intent = json.load(f)

    print(f"\n📥 Intent loaded:")
    print(f"   Type: {intent['intent_type']}")
    print(f"   Subsystem: {intent['data']['subsystem']}")
    print(f"   Seed fix: {intent['data']['seed_fix']}")

    # Create runner
    runner = ConfigTuningRunner()

    print(f"\n🚀 Running config tuning...")
    run = runner.run(intent['data'])

    print(f"\n📊 Results:")
    print(f"   Run ID: {run.run_id}")
    print(f"   Status: {run.status}")
    print(f"   Candidates tested: {len(run.candidates_tested)}")
    print(f"   Duration: {run.duration_s:.1f}s")

    if run.best_candidate:
        print(f"\n✅ Best candidate:")
        print(f"   ID: {run.best_candidate.candidate_id}")
        print(f"   Config: {run.best_candidate.candidate}")
        print(f"   Fitness: {run.best_candidate.fitness:.3f}")
        print(f"   Status: {run.best_candidate.status}")

    if run.promoted:
        print(f"\n🎉 Promotion created:")
        print(f"   Path: {run.promotion_path}")

    # Show all candidate results
    print(f"\n📋 All candidates:")
    for i, result in enumerate(run.candidates_tested):
        print(f"   {i+1}. {result.candidate} → status={result.status}, fitness={result.fitness:.3f}")

    print("\n" + "=" * 60)
    print("✓ Test complete")
    print("=" * 60)

    return 0

if __name__ == "__main__":
    sys.exit(main())
