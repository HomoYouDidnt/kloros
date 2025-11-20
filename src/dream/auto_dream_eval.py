#!/usr/bin/env python3
"""
Automatic D-REAM Evaluation Trigger

Called after PHASE window completion to automatically evaluate candidates.
Guards ensure we only run on valid PHASE outputs.
"""
import os
import sys
from datetime import datetime

# Add parent to path
sys.path.insert(0, "/home/kloros")

from src.phase.hooks import on_phase_window_complete


def get_latest_phase_window() -> str:
    """
    Determine the latest PHASE window/episode ID.

    For now, uses timestamp. In production, would read from PHASE state.
    """
    return datetime.utcnow().strftime("%Y-%m-%dT%H-%M")


def main():
    """
    Main entry point for automatic D-REAM evaluation.

    Can be called:
    1. With episode_id argument: auto_dream_eval.py <episode_id>
    2. Without arguments: auto-detects latest PHASE window
    """
    if len(sys.argv) > 1:
        episode_id = sys.argv[1]
        print(f"[auto_dream] Evaluating explicit episode: {episode_id}")
    else:
        episode_id = get_latest_phase_window()
        print(f"[auto_dream] Auto-detected episode: {episode_id}")

    try:
        # The guards in on_phase_window_complete will check:
        # - phase_raw/<episode>.jsonl exists
        # - File has at least 1 line
        on_phase_window_complete(episode_id)
        print(f"[auto_dream] ✓ D-REAM evaluation complete for {episode_id}")
    except Exception as e:
        print(f"[auto_dream] ✗ D-REAM evaluation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
