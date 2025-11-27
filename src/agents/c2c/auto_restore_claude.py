#!/usr/bin/env python3
"""
Auto-restore script for Claude Code sessions.

Run at session start to load previous semantic state.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.c2c.claude_bridge import ClaudeC2CManager


def restore_latest_session():
    """Load and display latest session state for manual continuation."""
    manager = ClaudeC2CManager()

    latest = manager.get_latest_session()
    if not latest:
        print("No previous Claude session state found.")
        print("This is the first C2C-enabled session.")
        return None

    print("=" * 60)
    print("🔄 RESTORING CLAUDE SESSION CONTEXT")
    print("=" * 60)
    print()

    resume_prompt = latest.generate_resume_prompt()
    print(resume_prompt)

    print()
    print("=" * 60)
    print("✅ Session context loaded. Continue from where we left off.")
    print("=" * 60)

    return latest


def create_session_snapshot():
    """Create snapshot of current session (call at session end)."""
    from src.c2c.claude_bridge import capture_current_session
    result = capture_current_session()
    print(f"✅ Session snapshot saved: {result['session_id']}")
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Claude C2C session management")
    parser.add_argument(
        "action",
        choices=["restore", "save", "list"],
        help="Action to perform"
    )

    args = parser.parse_args()

    if args.action == "restore":
        restore_latest_session()
    elif args.action == "save":
        create_session_snapshot()
    elif args.action == "list":
        manager = ClaudeC2CManager()
        sessions = manager.list_sessions()
        print(f"Available Claude sessions: {len(sessions)}\n")
        for session in sessions:
            print(f"  {session['session_id']}")
            print(f"    Tasks: {session['completed_tasks']}, "
                  f"Discoveries: {session['key_discoveries']}")
            print(f"    Timestamp: {session['timestamp']}")
            print()
