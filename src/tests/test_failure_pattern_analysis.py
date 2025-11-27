#!/usr/bin/env python3
"""
Test suite for failure pattern analysis (Phase 2.3).

Tests the analyze_failure_patterns() method and its helper functions
to ensure correct pattern detection and insight generation.
"""

import os
import sys
import tempfile
import time
import json
from pathlib import Path
from datetime import datetime, timedelta

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    from src.memory import (
        Event,
        EventType,
        MemoryStore,
    )
    print("✅ Memory modules imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

try:
    from src.consciousness.cognitive_actions_subscriber import CognitiveActionHandler
    print("✅ CognitiveActionHandler imported successfully")
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)


class FailurePatternAnalysisTester:
    """Test suite for failure pattern analysis."""

    def __init__(self):
        """Initialize test environment."""
        self.temp_dir = tempfile.mkdtemp(prefix="kloros_failure_test_")
        self.db_path = os.path.join(self.temp_dir, "test_failures.db")
        self.log_path = os.path.join(self.temp_dir, "actions.log")

        self.store = MemoryStore(self.db_path)
        self.handler = CognitiveActionHandler()
        self.handler.memory_store = self.store
        self.handler.action_log_path = Path(self.log_path)

        print(f"✅ Test environment initialized (DB: {self.db_path})")

    def test_empty_failure_list(self) -> bool:
        """Test analysis with no recent failures."""
        print("\n🧪 Testing: Empty failure list...")

        try:
            result = self.handler.analyze_failure_patterns(
                root_causes=['sporadic_errors'],
                actions=['monitor_system']
            )

            assert result is True, "Should succeed with no failures"
            print("  ✅ Handled empty failure list correctly")
            return True

        except Exception as e:
            print(f"  ❌ Test failed: {e}")
            return False

    def test_single_error_type_pattern(self) -> bool:
        """Test pattern identification with single error type."""
        print("\n🧪 Testing: Single error type pattern...")

        try:
            now = time.time()

            for i in range(5):
                event = Event(
                    timestamp=now - (i * 100),
                    event_type=EventType.TOOL_EXECUTION,
                    content=f"Tool execution failed",
                    metadata={
                        'success': False,
                        'error_type': 'connection_timeout',
                        'tool_name': 'api_call'
                    },
                    conversation_id=None
                )
                self.store.store_event(event)

            failures = self.handler._get_recent_failures(days=7)
            assert len(failures) >= 5, f"Expected 5+ failures, got {len(failures)}"

            patterns = self.handler._identify_patterns(failures)
            assert 'connection_timeout' in patterns['error_types'], "Should identify error type"
            assert patterns['error_types']['connection_timeout'] >= 5, "Should count errors correctly"

            insights = self.handler._generate_insights(patterns, ['repeated_timeouts'])
            assert len(insights['findings']) > 0, "Should generate findings"
            assert 'connection_timeout' in insights['findings'][0], "Should mention error type"

            print(f"  ✅ Identified {patterns['error_types']['connection_timeout']} timeout errors")
            print(f"  ✅ Generated {len(insights['findings'])} findings")
            return True

        except Exception as e:
            print(f"  ❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def test_multiple_tool_failures(self) -> bool:
        """Test pattern identification across multiple tools."""
        print("\n🧪 Testing: Multiple tool failures...")

        try:
            now = time.time()
            tools = ['tool_a', 'tool_b', 'tool_c']
            error_counts = {
                'tool_a': 3,
                'tool_b': 2,
                'tool_c': 1
            }

            for tool in tools:
                for i in range(error_counts[tool]):
                    event = Event(
                        timestamp=now - (i * 50),
                        event_type=EventType.TOOL_EXECUTION,
                        content=f"{tool} failed",
                        metadata={
                            'success': False,
                            'error_type': 'execution_failed',
                            'tool_name': tool
                        },
                        conversation_id=None
                    )
                    self.store.store_event(event)

            failures = self.handler._get_recent_failures(days=7)
            patterns = self.handler._identify_patterns(failures)

            assert 'tool_a' in patterns['common_tools'], "Should track tool_a"
            assert patterns['common_tools']['tool_a'] >= 3, "Should count tool_a failures"
            assert patterns['common_tools']['tool_a'] > patterns['common_tools']['tool_b'], \
                "Should rank by frequency"

            insights = self.handler._generate_insights(patterns, [])
            assert any('tool' in finding for finding in insights['findings']), \
                "Should mention failing tools"

            print(f"  ✅ Identified {len(patterns['common_tools'])} tools with failures")
            print(f"  ✅ Ranked by frequency: {sorted(patterns['common_tools'].items(), key=lambda x: x[1], reverse=True)}")
            return True

        except Exception as e:
            print(f"  ❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def test_temporal_clustering(self) -> bool:
        """Test detection of failures clustered in time."""
        print("\n🧪 Testing: Temporal clustering detection...")

        try:
            now = time.time()

            for i in range(4):
                event = Event(
                    timestamp=now - (i * 10),
                    event_type=EventType.ERROR_OCCURRED,
                    content=f"Error occurred",
                    metadata={
                        'error_type': 'system_error',
                        'tool_name': 'system'
                    },
                    conversation_id=None
                )
                self.store.store_event(event)

            failures = self.handler._get_recent_failures(days=7)
            patterns = self.handler._identify_patterns(failures)

            assert len(patterns['failure_times']) >= 4, "Should track failure times"

            time_range = max(patterns['failure_times']) - min(patterns['failure_times'])
            assert time_range < 3600, "Failures should be within 1 hour"

            insights = self.handler._generate_insights(patterns, ['burst_failures'])
            assert any('short time window' in f for f in insights['findings']), \
                "Should detect temporal clustering"

            print(f"  ✅ Detected {len(patterns['failure_times'])} failures within {time_range}s")
            print(f"  ✅ Generated temporal insight: {[f for f in insights['findings'] if 'window' in f]}")
            return True

        except Exception as e:
            print(f"  ❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def test_storage_to_episodic_memory(self) -> bool:
        """Test that analysis is stored to episodic memory."""
        print("\n🧪 Testing: Storage to episodic memory...")

        try:
            now = time.time()

            event = Event(
                timestamp=now,
                event_type=EventType.TOOL_EXECUTION,
                content="Tool failed",
                metadata={
                    'success': False,
                    'error_type': 'test_error',
                    'tool_name': 'test_tool'
                },
                conversation_id=None
            )
            self.store.store_event(event)

            failures = self.handler._get_recent_failures(days=7)
            patterns = self.handler._identify_patterns(failures)
            insights = self.handler._generate_insights(patterns, ['test_cause'])

            success = self.handler._store_failure_analysis(
                insights,
                root_causes=['test_cause'],
                actions=['test_action']
            )

            assert success is True, "Storage should succeed"

            stored_events = self.store.get_events(limit=10)
            self_reflection_events = [
                e for e in stored_events
                if e.event_type == EventType.SELF_REFLECTION
            ]

            assert len(self_reflection_events) > 0, "Should have stored analysis"
            assert 'Failure pattern analysis' in self_reflection_events[-1].content, \
                "Should have analysis content"

            metadata = self_reflection_events[-1].metadata
            assert 'findings' in metadata, "Should store findings"
            assert 'recommendations' in metadata, "Should store recommendations"
            assert 'root_causes' in metadata, "Should preserve root causes"

            print(f"  ✅ Stored analysis successfully (event_id: {self_reflection_events[-1].id})")
            print(f"  ✅ Metadata includes: findings, recommendations, root_causes")
            return True

        except Exception as e:
            print(f"  ❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def test_full_analysis_workflow(self) -> bool:
        """Test complete failure pattern analysis workflow."""
        print("\n🧪 Testing: Full analysis workflow...")

        try:
            now = time.time()

            error_scenarios = [
                ('connection_error', 'api_call', 3),
                ('timeout', 'database', 2),
                ('parse_error', 'json_parser', 1),
            ]

            for error_type, tool, count in error_scenarios:
                for i in range(count):
                    event = Event(
                        timestamp=now - (i * 5),
                        event_type=EventType.TOOL_EXECUTION,
                        content=f"{tool} failed with {error_type}",
                        metadata={
                            'success': False,
                            'error_type': error_type,
                            'tool_name': tool
                        },
                        conversation_id=None
                    )
                    self.store.store_event(event)

            result = self.handler.analyze_failure_patterns(
                root_causes=['multiple_tool_failures'],
                actions=['review_tools', 'add_retry_logic']
            )

            assert result is True, "Full workflow should succeed"

            stored_events = self.store.get_events(limit=10)
            self_reflection_events = [
                e for e in stored_events
                if e.event_type == EventType.SELF_REFLECTION
            ]

            assert len(self_reflection_events) > 0, "Should have created analysis event"

            print(f"  ✅ Successfully completed full analysis workflow")
            print(f"  ✅ Processed 6 failures across 3 tools")
            print(f"  ✅ Stored analysis to episodic memory")
            return True

        except Exception as e:
            print(f"  ❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run_all_tests(self) -> bool:
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("🧪 FAILURE PATTERN ANALYSIS TEST SUITE")
        print("=" * 60)

        tests = [
            ("Empty failure list", self.test_empty_failure_list),
            ("Single error type pattern", self.test_single_error_type_pattern),
            ("Multiple tool failures", self.test_multiple_tool_failures),
            ("Temporal clustering", self.test_temporal_clustering),
            ("Storage to episodic memory", self.test_storage_to_episodic_memory),
            ("Full analysis workflow", self.test_full_analysis_workflow),
        ]

        results = []
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
            except Exception as e:
                print(f"\n❌ Unexpected error in {test_name}: {e}")
                import traceback
                traceback.print_exc()
                results.append((test_name, False))

        print("\n" + "=" * 60)
        print("📊 TEST RESULTS")
        print("=" * 60)

        passed = sum(1 for _, result in results if result)
        total = len(results)

        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status} | {test_name}")

        print("=" * 60)
        print(f"Result: {passed}/{total} tests passed")

        if passed == total:
            print("🎉 All tests passed!")
            return True
        else:
            print(f"⚠️ {total - passed} test(s) failed")
            return False


def main():
    """Run the test suite."""
    tester = FailurePatternAnalysisTester()

    try:
        success = tester.run_all_tests()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
