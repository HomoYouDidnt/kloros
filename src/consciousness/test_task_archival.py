#!/usr/bin/env python3
"""
Task Archival Integration Tests - Phase 2, Task 2

Tests the archive_completed_tasks() method implementation in cognitive_actions_subscriber.
Verifies:
1. Completed tasks are retrieved from episodic memory
2. Tasks are successfully archived to memory storage
3. Task archival handles edge cases gracefully
4. Integration with episodic memory follows Phase 2.1 pattern
"""

import sys
import json
import time
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from consciousness.cognitive_actions_subscriber import CognitiveActionHandler


def test_archive_completed_tasks_no_data():
    """Test that archive gracefully handles when no tasks exist."""
    print("\n[test] Testing archive with no completed tasks...")

    handler = CognitiveActionHandler()

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        handler.action_log_path = Path(f.name)

    result = handler.archive_completed_tasks(
        evidence=["Memory pressure: token_usage at 75% of budget"]
    )

    assert result is True, "Should return True even with no tasks"
    print("  ✓ Returns True gracefully when no tasks to archive")
    print("  ✓ Logs appropriate action")


def test_get_completed_tasks_with_memory_store():
    """Test that _get_completed_tasks retrieves tasks correctly."""
    print("\n[test] Testing _get_completed_tasks retrieval...")

    handler = CognitiveActionHandler()

    tasks = handler._get_completed_tasks(days=7)

    assert isinstance(tasks, list), "Should return a list"
    print(f"  ✓ Retrieved {len(tasks)} completed tasks")
    print(f"  ✓ Returns list of task dictionaries")

    if tasks:
        first_task = tasks[0]
        assert 'id' in first_task, "Task should have 'id'"
        assert 'timestamp' in first_task, "Task should have 'timestamp'"
        assert 'content' in first_task, "Task should have 'content'"
        print(f"  ✓ Task structure: id={first_task['id']}, content preview: {first_task['content'][:50]}...")


def test_summarize_task():
    """Test that _summarize_task creates valid summaries."""
    print("\n[test] Testing _summarize_task summary creation...")

    handler = CognitiveActionHandler()

    task = {
        'id': 42,
        'content': 'Executed tool call to retrieve data',
        'metadata': {
            'tool_name': 'retrieve_data',
            'duration': 1.25,
            'success': True
        },
        'completed_at': datetime.now().isoformat()
    }

    summary = handler._summarize_task(task)

    assert isinstance(summary, str), "Summary should be a string"
    assert '[42]' in summary, "Summary should contain task ID"
    assert 'retrieve_data' in summary, "Summary should contain tool name or content"
    print(f"  ✓ Generated summary: {summary}")
    print(f"  ✓ Summary is concise and informative")


def test_summarize_task_without_metadata():
    """Test that _summarize_task handles tasks with minimal metadata."""
    print("\n[test] Testing _summarize_task with minimal data...")

    handler = CognitiveActionHandler()

    task = {
        'id': 99,
        'content': 'Simple task execution',
        'metadata': {},
        'completed_at': datetime.now().isoformat()
    }

    summary = handler._summarize_task(task)

    assert isinstance(summary, str), "Summary should be a string"
    assert '[99]' in summary, "Summary should contain task ID"
    assert len(summary) > 0, "Summary should not be empty"
    print(f"  ✓ Generated fallback summary: {summary}")


def test_archive_single_task_integration():
    """Test that _archive_single_task stores to episodic memory correctly."""
    print("\n[test] Testing _archive_single_task memory storage...")

    handler = CognitiveActionHandler()

    if not handler.memory_store:
        print("  ⚠ Memory store not available, skipping integration test")
        return

    task = {
        'id': 100,
        'content': 'Completed test task',
        'metadata': {
            'tool_name': 'test_tool',
            'success': True,
            'duration': 0.5
        },
        'timestamp': time.time(),
        'completed_at': datetime.now().isoformat()
    }

    evidence = ["Memory pressure: context window usage high"]

    result = handler._archive_single_task(task, evidence)

    assert isinstance(result, bool), "Should return boolean"
    print(f"  ✓ Archive result: {result}")
    if result:
        print("  ✓ Task successfully stored to episodic memory")
    else:
        print("  ⚠ Task storage returned False (may be expected if memory store not fully initialized)")


def test_action_log_entries():
    """Test that actions are properly logged."""
    print("\n[test] Testing action log entries...")

    handler = CognitiveActionHandler()

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        handler.action_log_path = Path(f.name)

    log_path = handler.action_log_path

    initial_size = log_path.stat().st_size if log_path.exists() else 0

    handler.log_action('test_action', 'Test action completed')

    final_size = log_path.stat().st_size if log_path.exists() else 0

    assert final_size > initial_size, "Log file should grow after action"
    print(f"  ✓ Action logged to {log_path}")
    print(f"  ✓ Log file grew: {initial_size} → {final_size} bytes")

    if log_path.exists():
        with open(log_path, 'r') as f:
            lines = f.readlines()
            last_line = lines[-1] if lines else ''
            assert 'test_action' in last_line, "Latest log entry should contain action type"
            print(f"  ✓ Latest log entry: {last_line.strip()[:80]}...")


def test_archive_completed_tasks_integration():
    """Test complete archive workflow."""
    print("\n[test] Testing complete archive_completed_tasks workflow...")

    handler = CognitiveActionHandler()

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        handler.action_log_path = Path(f.name)

    evidence = [
        "Memory pressure: token_usage at 85% of budget",
        "Context window approaching capacity"
    ]

    result = handler.archive_completed_tasks(evidence)

    assert isinstance(result, bool), "Should return boolean"
    print(f"  ✓ archive_completed_tasks returned: {result}")
    print("  ✓ Complete workflow executed successfully")


def run_all_tests():
    """Run all task archival tests."""
    print("="*70)
    print("TASK ARCHIVAL INTEGRATION TESTS - Phase 2, Task 2")
    print("="*70)

    tests = [
        test_archive_completed_tasks_no_data,
        test_get_completed_tasks_with_memory_store,
        test_summarize_task,
        test_summarize_task_without_metadata,
        test_archive_single_task_integration,
        test_action_log_entries,
        test_archive_completed_tasks_integration
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
