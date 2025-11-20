#!/usr/bin/env python3
"""
Run PHASE Coding Domain

Executes overnight coding runs (3-7am schedule)
"""
import sys
sys.path.insert(0, '/home/kloros')

from pathlib import Path
from src.phase.domains.code_repair import (
    CodeRepairConfig,
    run_overnight_code_repair
)
from src.dev_agent.llm_integration import create_llm_callable

def main():
    """Run overnight code repair PHASE."""
    print("=== KLoROS PHASE: Code Repair Domain ===\n")

    # Configuration
    config = CodeRepairConfig(
        repo_root=Path("/home/kloros"),
        max_attempts_per_bug=3,
        fast_test_filter="not slow and not e2e",
        timeout_per_attempt_sec=600,
        enable_self_play=False,  # Disable for initial run
        enable_heuristic_evolution=False,
        max_total_time_sec=14400,  # 4 hours
        max_memory_mb=4096,
        max_cpu_percent=50
    )

    # LLM callable
    llm = create_llm_callable(model="qwen2.5-coder:7b")

    # Run phases
    try:
        summary = run_overnight_code_repair(
            repo_root=config.repo_root,
            llm_callable=llm,
            config=config
        )

        print("\n=== Run Summary ===")
        print(f"Total duration: {summary['total_duration_sec']:.1f}s")
        print(f"Bugs fixed: {summary['bugs_fixed']}")
        print(f"Diffs applied: {summary['diffs_applied']}")
        print(f"Repair@3: {summary['repair_at_3']:.2%}")

        print(f"\nChangelog: /home/kloros/.kloros/code_changelog.md")
        print(f"Metrics: /home/kloros/.kloros/phase_code_metrics.json")

        return summary['bugs_fixed'] > 0

    except Exception as e:
        print(f"\n✗ Error during PHASE run: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
