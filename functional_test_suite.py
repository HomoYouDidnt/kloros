#!/usr/bin/env python3
"""
KLoROS Functional Test Suite
Deep functional tests of critical subsystems
"""

import sys
import os
import traceback
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
import tempfile
import numpy as np

sys.path.insert(0, '/home/kloros/src')
sys.path.insert(0, '/home/kloros')

class TestStatus(Enum):
    PASS = "✅ PASS"
    FAIL = "❌ FAIL"
    WARN = "⚠️  WARN"

@dataclass
class TestResult:
    subsystem: str
    test_name: str
    status: TestStatus
    message: str
    root_cause: Optional[str] = None
    suggested_fix: Optional[str] = None

class FunctionalTestSuite:
    def __init__(self):
        self.results: List[TestResult] = []

    def log(self, msg: str):
        print(f"[FUNC-TEST] {msg}")

    def add_result(self, subsystem: str, test_name: str, status: TestStatus,
                   message: str, root_cause: str = None, suggested_fix: str = None):
        result = TestResult(subsystem, test_name, status, message, root_cause, suggested_fix)
        self.results.append(result)
        print(f"{status.value} {subsystem}.{test_name}: {message}")
        if root_cause:
            print(f"    Root Cause: {root_cause}")
        if suggested_fix:
            print(f"    Fix: {suggested_fix}")

    def test_memory_storage(self):
        """Functional test: Memory storage and retrieval"""
        self.log("Testing memory storage functionality")

        try:
            from kloros_memory import MemoryStore, EventType

            # Create temp database
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
                db_path = tmp.name

            try:
                store = MemoryStore(db_path=db_path)

                # Test 1: Store event
                test_event = {
                    'timestamp': 1234567890.0,
                    'event_type': EventType.USER_INPUT,
                    'content': 'test user input',
                    'metadata': {'test': 'value'},
                }

                event_id = store.store_event(**test_event)
                if event_id:
                    self.add_result("Memory", "store_event", TestStatus.PASS,
                                  f"Event stored with ID {event_id}")
                else:
                    self.add_result("Memory", "store_event", TestStatus.FAIL,
                                  "store_event returned None",
                                  root_cause="Event storage failed",
                                  suggested_fix="Check MemoryStore.store_event() implementation")

                # Test 2: Get recent events
                if hasattr(store, 'get_recent_events'):
                    recent = store.get_recent_events(limit=10)
                    if recent and len(recent) > 0:
                        self.add_result("Memory", "get_recent_events", TestStatus.PASS,
                                      f"Retrieved {len(recent)} recent events")
                    else:
                        self.add_result("Memory", "get_recent_events", TestStatus.WARN,
                                      "No events retrieved",
                                      suggested_fix="Verify event was stored correctly")
                else:
                    self.add_result("Memory", "get_recent_events", TestStatus.WARN,
                                  "get_recent_events method not found",
                                  suggested_fix="Check MemoryStore API")

                # Test 3: Event types
                event_types = [e.name for e in EventType]
                critical_types = ['USER_INPUT', 'LLM_RESPONSE', 'WAKE_DETECTED', 'SYSTEM_ERROR']
                missing = [t for t in critical_types if t not in event_types]

                if not missing:
                    self.add_result("Memory", "event_types", TestStatus.PASS,
                                  f"All {len(critical_types)} critical event types present")
                else:
                    self.add_result("Memory", "event_types", TestStatus.WARN,
                                  f"Missing event types: {missing}",
                                  suggested_fix="Add missing EventType enum values")

            finally:
                # Cleanup
                if os.path.exists(db_path):
                    os.unlink(db_path)
                wal_file = db_path + '-wal'
                if os.path.exists(wal_file):
                    os.unlink(wal_file)
                shm_file = db_path + '-shm'
                if os.path.exists(shm_file):
                    os.unlink(shm_file)

        except Exception as e:
            self.add_result("Memory", "storage_test", TestStatus.FAIL,
                          "Memory storage test failed",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix="Fix MemoryStore implementation")

    def test_vad_detection(self):
        """Functional test: Voice activity detection"""
        self.log("Testing VAD detection functionality")

        try:
            from audio.vad import detect_voiced_segments, VADMetrics

            # Generate test audio: 1 second of silence, 1 second of "voice" (noise)
            sample_rate = 16000
            silence = np.zeros(sample_rate, dtype=np.float32)
            voice = np.random.normal(0, 0.1, sample_rate).astype(np.float32)  # Louder noise
            audio = np.concatenate([silence, voice])

            # Test detection
            segments, metrics = detect_voiced_segments(
                audio=audio,
                sample_rate=sample_rate,
                threshold_dbfs=-30.0,
            )

            if isinstance(metrics, VADMetrics):
                self.add_result("VAD", "metrics", TestStatus.PASS,
                              f"VADMetrics returned: mean={metrics.dbfs_mean:.1f}dB, peak={metrics.dbfs_peak:.1f}dB")

                if metrics.frames_active > 0:
                    self.add_result("VAD", "detection", TestStatus.PASS,
                                  f"Detected {metrics.frames_active}/{metrics.frames_total} active frames")
                else:
                    self.add_result("VAD", "detection", TestStatus.WARN,
                                  "No active frames detected (threshold may be too strict)",
                                  suggested_fix="Adjust test signal amplitude or threshold")

                if len(segments) > 0:
                    self.add_result("VAD", "segments", TestStatus.PASS,
                                  f"Found {len(segments)} voice segments")
                else:
                    self.add_result("VAD", "segments", TestStatus.WARN,
                                  "No segments extracted",
                                  suggested_fix="Adjust min_active_ms or signal strength")
            else:
                self.add_result("VAD", "metrics", TestStatus.FAIL,
                              "VADMetrics not returned",
                              root_cause=f"Got type {type(metrics)}",
                              suggested_fix="Check detect_voiced_segments return type")

        except Exception as e:
            self.add_result("VAD", "detection_test", TestStatus.FAIL,
                          "VAD detection test failed",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix="Fix VAD implementation")

    def test_wake_word(self):
        """Functional test: Wake word matching"""
        self.log("Testing wake word matching functionality")

        try:
            from fuzzy_wakeword import fuzzy_wake_match

            test_cases = [
                ("hello assistant", ["assistant", "computer"], True, "Exact match"),
                ("hey there", ["assistant", "computer"], False, "No match"),
                ("hello assistent", ["assistant"], True, "Fuzzy match (typo)"),
                ("", ["assistant"], False, "Empty transcript"),
            ]

            passed = 0
            failed = 0

            for transcript, wake_phrases, expected_match, description in test_cases:
                result = fuzzy_wake_match(transcript, wake_phrases, threshold=0.7)

                if result:
                    matched, score, phrase = result
                    if matched == expected_match:
                        passed += 1
                    else:
                        failed += 1
                        self.add_result("WakeWord", f"test_case_{description}", TestStatus.FAIL,
                                      f"Expected {expected_match}, got {matched}",
                                      root_cause=f"Transcript: '{transcript}', Phrase: '{phrase}', Score: {score}")
                else:
                    if not expected_match:
                        passed += 1
                    else:
                        failed += 1
                        self.add_result("WakeWord", f"test_case_{description}", TestStatus.FAIL,
                                      f"Expected match but got None",
                                      root_cause=f"Transcript: '{transcript}'")

            if failed == 0:
                self.add_result("WakeWord", "test_cases", TestStatus.PASS,
                              f"All {passed} test cases passed")
            else:
                self.add_result("WakeWord", "test_cases", TestStatus.WARN,
                              f"{passed} passed, {failed} failed",
                              suggested_fix="Review fuzzy matching algorithm")

        except Exception as e:
            self.add_result("WakeWord", "matching_test", TestStatus.FAIL,
                          "Wake word test failed",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix="Fix fuzzy_wakeword implementation")

    def test_llm_integration(self):
        """Functional test: LLM integration"""
        self.log("Testing LLM integration functionality")

        try:
            from reasoning.local_rag_backend import LocalRAGBackend

            # Create backend instance
            backend = LocalRAGBackend()

            if hasattr(backend, 'query') or hasattr(backend, 'generate'):
                self.add_result("LLM", "backend_init", TestStatus.PASS,
                              "LocalRAGBackend instantiated successfully")

                # Check for key methods
                methods = ['query', 'generate', 'answer', 'respond']
                found = [m for m in methods if hasattr(backend, m)]

                if found:
                    self.add_result("LLM", "methods", TestStatus.PASS,
                                  f"Found {len(found)} response methods: {found}")
                else:
                    self.add_result("LLM", "methods", TestStatus.WARN,
                                  "No standard response methods found",
                                  suggested_fix="Check LocalRAGBackend API")
            else:
                self.add_result("LLM", "backend_init", TestStatus.WARN,
                              "LocalRAGBackend missing standard methods",
                              suggested_fix="Verify LocalRAGBackend implementation")

        except Exception as e:
            self.add_result("LLM", "integration_test", TestStatus.FAIL,
                          "LLM integration test failed",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix="Fix LocalRAGBackend implementation")

    def test_introspection_tools(self):
        """Functional test: Introspection tools registry"""
        self.log("Testing introspection tools functionality")

        try:
            from introspection_tools import IntrospectionToolRegistry

            registry = IntrospectionToolRegistry()

            # Test 1: Get all tools
            if hasattr(registry, 'get_all_tools'):
                tools = registry.get_all_tools()
                tool_count = len(tools) if tools else 0

                if tool_count >= 60:
                    self.add_result("Introspection", "tool_count", TestStatus.PASS,
                                  f"Registry has {tool_count} tools (expected ~69)")

                    # Sample first few tools
                    sample_size = min(5, tool_count)
                    sample = list(tools)[:sample_size] if tools else []

                    if sample:
                        self.add_result("Introspection", "tool_sample", TestStatus.PASS,
                                      f"Sample tools: {[t.get('name', 'unnamed') if isinstance(t, dict) else str(t)[:30] for t in sample]}")
                else:
                    self.add_result("Introspection", "tool_count", TestStatus.WARN,
                                  f"Low tool count: {tool_count}",
                                  suggested_fix="Verify tool registration")
            else:
                self.add_result("Introspection", "get_tools", TestStatus.WARN,
                              "get_all_tools method not found",
                              suggested_fix="Check IntrospectionToolRegistry API")

            # Test 2: Tool invocation (if available)
            if hasattr(registry, 'invoke_tool') or hasattr(registry, 'call_tool'):
                self.add_result("Introspection", "invocation", TestStatus.PASS,
                              "Tool invocation method available")
            else:
                self.add_result("Introspection", "invocation", TestStatus.WARN,
                              "No tool invocation method found",
                              suggested_fix="Implement invoke_tool or call_tool")

        except Exception as e:
            self.add_result("Introspection", "registry_test", TestStatus.FAIL,
                          "Introspection test failed",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix="Fix IntrospectionToolRegistry implementation")

    def test_dream_system(self):
        """Functional test: D-REAM evolution system"""
        self.log("Testing D-REAM system functionality")

        try:
            # Check for D-REAM components
            dream_components = [
                ('dream.core', 'Core engine'),
                ('dream.runner', 'Runner'),
                ('dream.workers', 'Workers'),
            ]

            found = []
            for module, description in dream_components:
                try:
                    __import__(module)
                    found.append(description)
                except ImportError:
                    pass

            if found:
                self.add_result("D-REAM", "components", TestStatus.PASS,
                              f"D-REAM components found: {found}")
            else:
                self.add_result("D-REAM", "components", TestStatus.WARN,
                              "D-REAM components not importable",
                              suggested_fix="Check D-REAM module structure")

            # Check for evolutionary optimization
            try:
                from evolutionary_optimization import EvolutionaryOptimizer
                self.add_result("D-REAM", "evolution", TestStatus.PASS,
                              "EvolutionaryOptimizer found")
            except ImportError:
                self.add_result("D-REAM", "evolution", TestStatus.WARN,
                              "EvolutionaryOptimizer not found",
                              suggested_fix="Check evolutionary_optimization module")

        except Exception as e:
            self.add_result("D-REAM", "system_test", TestStatus.FAIL,
                          "D-REAM test failed",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix="Fix D-REAM implementation")

    def test_self_healing(self):
        """Functional test: Self-healing system"""
        self.log("Testing self-healing functionality")

        try:
            # Check for self-heal components
            from self_heal import events, executor, policy

            components = []
            if hasattr(events, 'HealthEvent'):
                components.append('events')
            if hasattr(executor, 'Executor') or hasattr(executor, 'execute'):
                components.append('executor')
            if hasattr(policy, 'Policy') or hasattr(policy, 'PolicyEngine'):
                components.append('policy')

            if len(components) >= 2:
                self.add_result("SelfHeal", "components", TestStatus.PASS,
                              f"Self-healing components found: {components}")
            elif components:
                self.add_result("SelfHeal", "components", TestStatus.WARN,
                              f"Partial self-healing: {components}",
                              suggested_fix="Implement missing components")
            else:
                self.add_result("SelfHeal", "components", TestStatus.FAIL,
                              "No self-healing components detected",
                              root_cause="Components not properly structured",
                              suggested_fix="Verify self_heal module structure")

        except Exception as e:
            self.add_result("SelfHeal", "system_test", TestStatus.FAIL,
                          "Self-healing test failed",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix="Fix self_heal implementation")

    def test_consciousness(self):
        """Functional test: Consciousness integration"""
        self.log("Testing consciousness system functionality")

        try:
            from consciousness import integration

            if hasattr(integration, 'ConsciousnessIntegration'):
                self.add_result("Consciousness", "integration", TestStatus.PASS,
                              "ConsciousnessIntegration found")

                # Check for key methods
                ci = integration.ConsciousnessIntegration
                methods = ['process', 'integrate', 'update']
                found = [m for m in methods if hasattr(ci, m)]

                if found:
                    self.add_result("Consciousness", "methods", TestStatus.PASS,
                                  f"Found methods: {found}")
            else:
                self.add_result("Consciousness", "integration", TestStatus.WARN,
                              "ConsciousnessIntegration not found",
                              suggested_fix="Check consciousness.integration module")

        except Exception as e:
            self.add_result("Consciousness", "system_test", TestStatus.FAIL,
                          "Consciousness test failed",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix="Fix consciousness implementation")

    def run_all_tests(self):
        """Run all functional tests"""
        print("=" * 80)
        print("KLoROS FUNCTIONAL TEST SUITE")
        print("Deep testing of critical subsystem functionality")
        print("=" * 80)
        print()

        print("\n=== P0: CRITICAL FUNCTIONALITY ===\n")
        self.test_memory_storage()
        self.test_vad_detection()
        self.test_wake_word()
        self.test_llm_integration()

        print("\n=== P1-P3: ADVANCED FUNCTIONALITY ===\n")
        self.test_introspection_tools()
        self.test_dream_system()
        self.test_self_healing()
        self.test_consciousness()

        self.generate_report()

    def generate_report(self):
        """Generate test report"""
        print("\n" + "=" * 80)
        print("FUNCTIONAL TEST REPORT")
        print("=" * 80)

        total = len(self.results)
        passes = sum(1 for r in self.results if r.status == TestStatus.PASS)
        failures = sum(1 for r in self.results if r.status == TestStatus.FAIL)
        warnings = sum(1 for r in self.results if r.status == TestStatus.WARN)

        print(f"\nTotal Functional Tests: {total}")
        print(f"✅ PASS: {passes} ({passes/total*100:.1f}%)")
        print(f"❌ FAIL: {failures} ({failures/total*100:.1f}%)")
        print(f"⚠️  WARN: {warnings} ({warnings/total*100:.1f}%)")

        if failures > 0:
            print("\n" + "=" * 80)
            print("FAILURES")
            print("=" * 80)
            for r in self.results:
                if r.status == TestStatus.FAIL:
                    print(f"\n{r.subsystem}.{r.test_name}: {r.message}")
                    if r.root_cause:
                        print(f"  Root Cause: {r.root_cause}")
                    if r.suggested_fix:
                        print(f"  Fix: {r.suggested_fix}")

        if warnings > 0:
            print("\n" + "=" * 80)
            print("WARNINGS")
            print("=" * 80)
            for r in self.results:
                if r.status == TestStatus.WARN:
                    print(f"\n{r.subsystem}.{r.test_name}: {r.message}")
                    if r.suggested_fix:
                        print(f"  Fix: {r.suggested_fix}")

        print("\n" + "=" * 80)
        print(f"Functional health score: {passes/total*100:.1f}%")
        print("=" * 80)

if __name__ == "__main__":
    suite = FunctionalTestSuite()
    try:
        suite.run_all_tests()
    except KeyboardInterrupt:
        print("\n\nTest suite interrupted")
        suite.generate_report()
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        traceback.print_exc()
        suite.generate_report()
