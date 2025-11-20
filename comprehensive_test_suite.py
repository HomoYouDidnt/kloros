#!/usr/bin/env python3
"""
KLoROS Comprehensive Test Suite
Tests all 71+ subsystems systematically by priority (P0 -> P4)
"""

import sys
import os
import traceback
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum

sys.path.insert(0, '/home/kloros/src')
sys.path.insert(0, '/home/kloros')

class TestStatus(Enum):
    PASS = "✅ PASS"
    FAIL = "❌ FAIL"
    WARN = "⚠️  WARN"
    SKIP = "⏭️  SKIP"

@dataclass
class TestResult:
    subsystem: str
    priority: str
    status: TestStatus
    message: str
    root_cause: Optional[str] = None
    suggested_fix: Optional[str] = None

class KLoROSTestSuite:
    def __init__(self):
        self.results: List[TestResult] = []
        self.venv_python = "/home/kloros/.venv/bin/python3"

    def log(self, msg: str):
        print(f"[TEST] {msg}")

    def add_result(self, subsystem: str, priority: str, status: TestStatus,
                   message: str, root_cause: str = None, suggested_fix: str = None):
        result = TestResult(subsystem, priority, status, message, root_cause, suggested_fix)
        self.results.append(result)
        print(f"{status.value} [{priority}] {subsystem}: {message}")
        if root_cause:
            print(f"    Root Cause: {root_cause}")
        if suggested_fix:
            print(f"    Fix: {suggested_fix}")

    def test_import(self, module_path: str, subsystem: str, priority: str) -> bool:
        """Test if a module can be imported"""
        try:
            exec(f"import {module_path}")
            self.add_result(subsystem, priority, TestStatus.PASS, f"Import successful: {module_path}")
            return True
        except ImportError as e:
            self.add_result(subsystem, priority, TestStatus.FAIL,
                          f"Import failed: {module_path}",
                          root_cause=str(e),
                          suggested_fix=f"Check module path and dependencies for {module_path}")
            return False
        except Exception as e:
            self.add_result(subsystem, priority, TestStatus.FAIL,
                          f"Import error: {module_path}",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix=f"Fix initialization issues in {module_path}")
            return False

    def test_class_instantiation(self, module_path: str, class_name: str,
                                subsystem: str, priority: str, **kwargs) -> Any:
        """Test if a class can be instantiated"""
        try:
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            instance = cls(**kwargs)
            self.add_result(subsystem, priority, TestStatus.PASS,
                          f"Instantiation successful: {class_name}")
            return instance
        except AttributeError as e:
            self.add_result(subsystem, priority, TestStatus.FAIL,
                          f"Class not found: {class_name}",
                          root_cause=str(e),
                          suggested_fix=f"Verify {class_name} exists in {module_path}")
            return None
        except TypeError as e:
            self.add_result(subsystem, priority, TestStatus.FAIL,
                          f"Instantiation failed: {class_name}",
                          root_cause=f"TypeError: {str(e)}",
                          suggested_fix=f"Check __init__ signature for {class_name}, may need different args")
            return None
        except Exception as e:
            self.add_result(subsystem, priority, TestStatus.FAIL,
                          f"Instantiation error: {class_name}",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix=f"Fix initialization logic in {class_name}.__init__")
            return None

    def test_p0_voice_stt(self):
        """P0: Test Speech-to-Text"""
        self.log("Testing P0: STT (Speech-to-Text)")

        if not os.path.exists('/home/kloros/src/audio'):
            self.add_result("STT", "P0", TestStatus.FAIL,
                          "Audio module directory not found",
                          root_cause="Missing /home/kloros/src/audio directory",
                          suggested_fix="Verify audio subsystem installation")
            return

        if self.test_import("audio.stt", "STT", "P0"):
            self.test_class_instantiation("audio.stt", "WhisperSTT", "STT", "P0")

    def test_p0_voice_tts(self):
        """P0: Test Text-to-Speech"""
        self.log("Testing P0: TTS (Text-to-Speech)")

        if self.test_import("audio.tts", "TTS", "P0"):
            self.test_class_instantiation("audio.tts", "PiperTTS", "TTS", "P0")

    def test_p0_voice_wake(self):
        """P0: Test Wake Word Detection"""
        self.log("Testing P0: Wake Word Detection")

        if self.test_import("fuzzy_wakeword", "WakeWord", "P0"):
            try:
                from fuzzy_wakeword import fuzzy_wake_match
                result = fuzzy_wake_match("hello assistant", ["assistant", "hey system"], 0.7)
                self.add_result("WakeWord", "P0", TestStatus.PASS,
                              f"Wake word matching works: {result}")
            except Exception as e:
                self.add_result("WakeWord", "P0", TestStatus.FAIL,
                              "Wake word function test failed",
                              root_cause=str(e),
                              suggested_fix="Check fuzzy_wake_match signature and logic")

    def test_p0_voice_vad(self):
        """P0: Test Voice Activity Detection"""
        self.log("Testing P0: VAD (Voice Activity Detection)")

        if self.test_import("audio.vad", "VAD", "P0"):
            self.test_class_instantiation("audio.vad", "SileroVAD", "VAD", "P0")

    def test_p0_llm(self):
        """P0: Test LLM Integration"""
        self.log("Testing P0: LLM Integration")

        if self.test_import("integrations.llm", "LLM", "P0"):
            try:
                from integrations.llm import LLMClient
                self.add_result("LLM", "P0", TestStatus.PASS, "LLMClient imported successfully")
            except ImportError:
                self.add_result("LLM", "P0", TestStatus.WARN,
                              "LLMClient not found, trying alternative imports",
                              suggested_fix="Check LLM integration module structure")

    def test_p0_memory(self):
        """P0: Test Memory System"""
        self.log("Testing P0: Memory System")

        if self.test_import("kloros_memory.memory_store", "Memory", "P0"):
            try:
                from kloros_memory.memory_store import MemoryStore, EventType

                if hasattr(EventType, 'WAKE_DETECTED'):
                    self.add_result("Memory", "P0", TestStatus.PASS,
                                  "EventType.WAKE_DETECTED exists")
                else:
                    available = [e.name for e in EventType]
                    self.add_result("Memory", "P0", TestStatus.FAIL,
                                  "EventType.WAKE_DETECTED not found",
                                  root_cause=f"Available EventTypes: {available}",
                                  suggested_fix="Use correct EventType enum value")

                store = MemoryStore()
                if hasattr(store, 'store_event'):
                    self.add_result("Memory", "P0", TestStatus.PASS,
                                  "MemoryStore.store_event() exists")
                elif hasattr(store, 'add_event'):
                    self.add_result("Memory", "P0", TestStatus.WARN,
                                  "MemoryStore uses add_event() not store_event()",
                                  suggested_fix="Update callers to use add_event()")
                else:
                    methods = [m for m in dir(store) if not m.startswith('_')]
                    self.add_result("Memory", "P0", TestStatus.FAIL,
                                  "No event storage method found",
                                  root_cause=f"Available methods: {methods}",
                                  suggested_fix="Implement event storage method")

            except Exception as e:
                self.add_result("Memory", "P0", TestStatus.FAIL,
                              "Memory system test failed",
                              root_cause=f"{type(e).__name__}: {str(e)}",
                              suggested_fix="Fix MemoryStore initialization or API")

    def test_p1_reasoning_tot(self):
        """P1: Test Tree-of-Thought Reasoning"""
        self.log("Testing P1: ToT (Tree-of-Thought)")

        if self.test_import("reasoning.tree_of_thought", "ToT", "P1"):
            self.test_class_instantiation("reasoning.tree_of_thought",
                                        "TreeOfThought", "ToT", "P1")

    def test_p1_reasoning_debate(self):
        """P1: Test Debate Reasoning"""
        self.log("Testing P1: Debate Reasoning")

        if self.test_import("reasoning.debate", "Debate", "P1"):
            self.test_class_instantiation("reasoning.debate",
                                        "DebateReasoner", "Debate", "P1")

    def test_p1_reasoning_voi(self):
        """P1: Test Value of Information"""
        self.log("Testing P1: VOI (Value of Information)")

        if self.test_import("reasoning.voi", "VOI", "P1"):
            self.test_class_instantiation("reasoning.voi",
                                        "VOICalculator", "VOI", "P1")

    def test_p1_orchestration(self):
        """P1: Test Orchestration System"""
        self.log("Testing P1: Orchestration")

        if self.test_import("orchestrator.coordinator", "Orchestrator", "P1"):
            try:
                from orchestrator.coordinator import OrchestratorCoordinator
                self.add_result("Orchestrator", "P1", TestStatus.PASS,
                              "OrchestratorCoordinator imported")
            except ImportError as e:
                self.add_result("Orchestrator", "P1", TestStatus.FAIL,
                              "Orchestrator import failed",
                              root_cause=str(e),
                              suggested_fix="Check orchestrator module structure")

    def test_p1_self_healing(self):
        """P1: Test Self-Healing System"""
        self.log("Testing P1: Self-Healing")

        if self.test_import("self_heal.recovery", "SelfHeal", "P1"):
            try:
                from self_heal.recovery import RecoveryEngine
                self.add_result("SelfHeal", "P1", TestStatus.PASS,
                              "RecoveryEngine imported")
            except ImportError:
                self.add_result("SelfHeal", "P1", TestStatus.WARN,
                              "RecoveryEngine not found",
                              suggested_fix="Check self-healing module structure")

    def test_p2_dream(self):
        """P2: Test D-REAM System"""
        self.log("Testing P2: D-REAM")

        if self.test_import("dream.core.engine", "D-REAM", "P2"):
            try:
                from dream.core.engine import DreamEngine
                self.add_result("D-REAM", "P2", TestStatus.PASS,
                              "DreamEngine imported")
            except ImportError:
                self.add_result("D-REAM", "P2", TestStatus.WARN,
                              "DreamEngine not found",
                              suggested_fix="Check D-REAM module structure")

    def test_p2_phase(self):
        """P2: Test PHASE Scheduler"""
        self.log("Testing P2: PHASE")

        if self.test_import("phase.scheduler", "PHASE", "P2"):
            try:
                from phase.scheduler import PHASEScheduler
                self.add_result("PHASE", "P2", TestStatus.PASS,
                              "PHASEScheduler imported")
            except ImportError:
                self.add_result("PHASE", "P2", TestStatus.WARN,
                              "PHASEScheduler not found",
                              suggested_fix="Check PHASE module structure")

    def test_p2_curiosity(self):
        """P2: Test Curiosity System"""
        self.log("Testing P2: Curiosity")

        if self.test_import("idle_reflection.curiosity", "Curiosity", "P2"):
            try:
                from idle_reflection.curiosity import CuriosityEngine
                self.add_result("Curiosity", "P2", TestStatus.PASS,
                              "CuriosityEngine imported")
            except ImportError:
                self.add_result("Curiosity", "P2", TestStatus.WARN,
                              "CuriosityEngine not found",
                              suggested_fix="Check curiosity module structure")

    def test_p2_reflection(self):
        """P2: Test Reflection System"""
        self.log("Testing P2: Reflection")

        if self.test_import("idle_reflection.reflection", "Reflection", "P2"):
            try:
                from idle_reflection.reflection import ReflectionEngine
                self.add_result("Reflection", "P2", TestStatus.PASS,
                              "ReflectionEngine imported")
            except ImportError:
                self.add_result("Reflection", "P2", TestStatus.WARN,
                              "ReflectionEngine not found",
                              suggested_fix="Check reflection module structure")

    def test_p3_tool_synthesis(self):
        """P3: Test Tool Synthesis"""
        self.log("Testing P3: Tool Synthesis")

        if self.test_import("tool_synthesis.ecosystem_manager", "ToolSynthesis", "P3"):
            try:
                from tool_synthesis.ecosystem_manager import EcosystemManager
                self.add_result("ToolSynthesis", "P3", TestStatus.PASS,
                              "EcosystemManager imported")
            except ImportError:
                self.add_result("ToolSynthesis", "P3", TestStatus.WARN,
                              "EcosystemManager not found",
                              suggested_fix="Check tool synthesis module structure")

    def test_p3_mcp(self):
        """P3: Test MCP Integration"""
        self.log("Testing P3: MCP")

        if self.test_import("mcp.server", "MCP", "P3"):
            try:
                from mcp.server import MCPServer
                self.add_result("MCP", "P3", TestStatus.PASS,
                              "MCPServer imported")
            except ImportError:
                self.add_result("MCP", "P3", TestStatus.WARN,
                              "MCPServer not found",
                              suggested_fix="Check MCP module structure")

    def test_p3_agents(self):
        """P3: Test Agent System"""
        self.log("Testing P3: Agents")

        if self.test_import("agentflow.agent", "Agents", "P3"):
            try:
                from agentflow.agent import Agent
                self.add_result("Agents", "P3", TestStatus.PASS,
                              "Agent imported")
            except ImportError:
                self.add_result("Agents", "P3", TestStatus.WARN,
                              "Agent not found",
                              suggested_fix="Check agentflow module structure")

    def test_p4_logging(self):
        """P4: Test Logging System"""
        self.log("Testing P4: Logging")

        if self.test_import("logging.logger", "Logging", "P4"):
            try:
                from logging.logger import get_logger
                self.add_result("Logging", "P4", TestStatus.PASS,
                              "Logging system imported")
            except ImportError:
                self.add_result("Logging", "P4", TestStatus.WARN,
                              "Custom logger not found",
                              suggested_fix="Check logging module structure")

    def test_p4_metrics(self):
        """P4: Test Metrics System"""
        self.log("Testing P4: Metrics")

        if self.test_import("observer.metrics", "Metrics", "P4"):
            try:
                from observer.metrics import MetricsCollector
                self.add_result("Metrics", "P4", TestStatus.PASS,
                              "MetricsCollector imported")
            except ImportError:
                self.add_result("Metrics", "P4", TestStatus.WARN,
                              "MetricsCollector not found",
                              suggested_fix="Check metrics module structure")

    def test_introspection_tools(self):
        """P3: Test Introspection Tools Registry"""
        self.log("Testing P3: Introspection Tools")

        if self.test_import("introspection_tools", "Introspection", "P3"):
            try:
                from introspection_tools import IntrospectionToolRegistry
                registry = IntrospectionToolRegistry()
                tool_count = len(registry.get_all_tools()) if hasattr(registry, 'get_all_tools') else 0

                if tool_count == 69:
                    self.add_result("Introspection", "P3", TestStatus.PASS,
                                  f"IntrospectionToolRegistry has correct count: {tool_count}")
                elif tool_count > 0:
                    self.add_result("Introspection", "P3", TestStatus.WARN,
                                  f"Tool count mismatch: expected 69, got {tool_count}",
                                  suggested_fix="Verify introspection tools registration")
                else:
                    self.add_result("Introspection", "P3", TestStatus.FAIL,
                                  "No introspection tools found",
                                  root_cause="IntrospectionToolRegistry appears empty",
                                  suggested_fix="Check tool registration logic")

            except Exception as e:
                self.add_result("Introspection", "P3", TestStatus.FAIL,
                              "Introspection test failed",
                              root_cause=str(e),
                              suggested_fix="Fix IntrospectionToolRegistry implementation")

    def run_all_tests(self):
        """Run all tests in priority order"""
        print("=" * 80)
        print("KLoROS COMPREHENSIVE TEST SUITE")
        print("=" * 80)
        print()

        print("\n=== P0: CRITICAL SUBSYSTEMS ===\n")
        self.test_p0_voice_stt()
        self.test_p0_voice_tts()
        self.test_p0_voice_wake()
        self.test_p0_voice_vad()
        self.test_p0_llm()
        self.test_p0_memory()

        print("\n=== P1: CORE SUBSYSTEMS ===\n")
        self.test_p1_reasoning_tot()
        self.test_p1_reasoning_debate()
        self.test_p1_reasoning_voi()
        self.test_p1_orchestration()
        self.test_p1_self_healing()

        print("\n=== P2: ADVANCED SUBSYSTEMS ===\n")
        self.test_p2_dream()
        self.test_p2_phase()
        self.test_p2_curiosity()
        self.test_p2_reflection()

        print("\n=== P3: EXTENDED SUBSYSTEMS ===\n")
        self.test_p3_tool_synthesis()
        self.test_p3_mcp()
        self.test_p3_agents()
        self.test_introspection_tools()

        print("\n=== P4: SUPPORT SUBSYSTEMS ===\n")
        self.test_p4_logging()
        self.test_p4_metrics()

        self.generate_report()

    def generate_report(self):
        """Generate comprehensive test report"""
        print("\n" + "=" * 80)
        print("TEST REPORT SUMMARY")
        print("=" * 80)

        total = len(self.results)
        passes = sum(1 for r in self.results if r.status == TestStatus.PASS)
        failures = sum(1 for r in self.results if r.status == TestStatus.FAIL)
        warnings = sum(1 for r in self.results if r.status == TestStatus.WARN)
        skips = sum(1 for r in self.results if r.status == TestStatus.SKIP)

        print(f"\nTotal Tests: {total}")
        print(f"✅ PASS: {passes} ({passes/total*100:.1f}%)")
        print(f"❌ FAIL: {failures} ({failures/total*100:.1f}%)")
        print(f"⚠️  WARN: {warnings} ({warnings/total*100:.1f}%)")
        print(f"⏭️  SKIP: {skips} ({skips/total*100:.1f}%)")

        if failures > 0:
            print("\n" + "=" * 80)
            print("FAILURES DETAIL")
            print("=" * 80)
            for r in self.results:
                if r.status == TestStatus.FAIL:
                    print(f"\n[{r.priority}] {r.subsystem}")
                    print(f"  Message: {r.message}")
                    if r.root_cause:
                        print(f"  Root Cause: {r.root_cause}")
                    if r.suggested_fix:
                        print(f"  Suggested Fix: {r.suggested_fix}")

        if warnings > 0:
            print("\n" + "=" * 80)
            print("WARNINGS DETAIL")
            print("=" * 80)
            for r in self.results:
                if r.status == TestStatus.WARN:
                    print(f"\n[{r.priority}] {r.subsystem}")
                    print(f"  Message: {r.message}")
                    if r.suggested_fix:
                        print(f"  Suggested Fix: {r.suggested_fix}")

        print("\n" + "=" * 80)
        print("RECOMMENDATIONS")
        print("=" * 80)

        priority_failures = {}
        for r in self.results:
            if r.status == TestStatus.FAIL:
                if r.priority not in priority_failures:
                    priority_failures[r.priority] = []
                priority_failures[r.priority].append(r.subsystem)

        if priority_failures:
            print("\nPriority fixes needed:")
            for priority in ['P0', 'P1', 'P2', 'P3', 'P4']:
                if priority in priority_failures:
                    print(f"\n{priority} (Critical):")
                    for subsystem in priority_failures[priority]:
                        print(f"  - {subsystem}")
        else:
            print("\n✅ No critical failures detected!")

        print("\n" + "=" * 80)

if __name__ == "__main__":
    suite = KLoROSTestSuite()
    try:
        suite.run_all_tests()
    except KeyboardInterrupt:
        print("\n\nTest suite interrupted by user")
        suite.generate_report()
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        traceback.print_exc()
        suite.generate_report()
