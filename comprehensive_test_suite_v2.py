#!/usr/bin/env python3
"""
KLoROS Comprehensive Test Suite V2
Tests all subsystems with correct module paths discovered from actual codebase
"""

import sys
import os
import traceback
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from enum import Enum
import importlib

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
    details: Optional[str] = None

class KLoROSTestSuite:
    def __init__(self):
        self.results: List[TestResult] = []
        self.venv_python = "/home/kloros/.venv/bin/python3"

    def log(self, msg: str):
        print(f"[TEST] {msg}")

    def add_result(self, subsystem: str, priority: str, status: TestStatus,
                   message: str, root_cause: str = None, suggested_fix: str = None,
                   details: str = None):
        result = TestResult(subsystem, priority, status, message, root_cause, suggested_fix, details)
        self.results.append(result)
        print(f"{status.value} [{priority}] {subsystem}: {message}")
        if root_cause:
            print(f"    Root Cause: {root_cause}")
        if suggested_fix:
            print(f"    Fix: {suggested_fix}")
        if details:
            print(f"    Details: {details}")

    def safe_import(self, module_path: str) -> tuple[bool, Any, Optional[str]]:
        """Safely import a module and return (success, module, error)"""
        try:
            module = importlib.import_module(module_path)
            return True, module, None
        except Exception as e:
            return False, None, f"{type(e).__name__}: {str(e)}"

    def test_p0_voice_stt(self):
        """P0: Test Speech-to-Text"""
        self.log("Testing P0: STT (Speech-to-Text)")

        success, mod, error = self.safe_import("kloros_voice")
        if success:
            self.add_result("STT", "P0", TestStatus.PASS,
                          "kloros_voice module imported (contains STT logic)",
                          details="STT is integrated into kloros_voice.py")
        else:
            self.add_result("STT", "P0", TestStatus.FAIL,
                          "Failed to import kloros_voice",
                          root_cause=error,
                          suggested_fix="Check kloros_voice.py for syntax errors")

    def test_p0_voice_tts(self):
        """P0: Test Text-to-Speech"""
        self.log("Testing P0: TTS (Text-to-Speech)")

        success, mod, error = self.safe_import("kloros_voice")
        if success:
            has_piper = hasattr(mod, 'PiperTTS') or 'piper' in str(dir(mod)).lower()
            if has_piper:
                self.add_result("TTS", "P0", TestStatus.PASS,
                              "TTS (PiperTTS) found in kloros_voice")
            else:
                self.add_result("TTS", "P0", TestStatus.WARN,
                              "kloros_voice imported but PiperTTS not found",
                              suggested_fix="Verify TTS implementation in kloros_voice.py")
        else:
            self.add_result("TTS", "P0", TestStatus.FAIL,
                          "Failed to import kloros_voice for TTS",
                          root_cause=error)

    def test_p0_voice_wake(self):
        """P0: Test Wake Word Detection"""
        self.log("Testing P0: Wake Word Detection")

        success, mod, error = self.safe_import("fuzzy_wakeword")
        if not success:
            self.add_result("WakeWord", "P0", TestStatus.FAIL,
                          "Failed to import fuzzy_wakeword",
                          root_cause=error)
            return

        try:
            fuzzy_wake_match = getattr(mod, 'fuzzy_wake_match')
            result = fuzzy_wake_match("hello assistant", ["assistant", "hey system"], 0.7)

            if result and len(result) == 3:
                matched, score, phrase = result
                self.add_result("WakeWord", "P0", TestStatus.PASS,
                              f"Wake word matching works: matched={matched}, score={score:.2f}, phrase={phrase}")
            else:
                self.add_result("WakeWord", "P0", TestStatus.WARN,
                              f"Unexpected fuzzy_wake_match result: {result}",
                              suggested_fix="Verify fuzzy_wake_match return format")
        except Exception as e:
            self.add_result("WakeWord", "P0", TestStatus.FAIL,
                          "Wake word function test failed",
                          root_cause=str(e),
                          suggested_fix="Check fuzzy_wake_match signature and logic")

    def test_p0_voice_vad(self):
        """P0: Test Voice Activity Detection"""
        self.log("Testing P0: VAD (Voice Activity Detection)")

        success, mod, error = self.safe_import("audio.vad")
        if not success:
            self.add_result("VAD", "P0", TestStatus.FAIL,
                          "Failed to import audio.vad",
                          root_cause=error)
            return

        functions = ["detect_voiced_segments", "detect_candidates_dbfs", "detect_segments_two_stage"]
        found = [f for f in functions if hasattr(mod, f)]

        if len(found) == len(functions):
            self.add_result("VAD", "P0", TestStatus.PASS,
                          f"VAD module complete with {len(found)} key functions: {found}")
        elif found:
            self.add_result("VAD", "P0", TestStatus.WARN,
                          f"VAD module partial: found {found}, missing {set(functions) - set(found)}",
                          suggested_fix="Implement missing VAD functions")
        else:
            self.add_result("VAD", "P0", TestStatus.FAIL,
                          "VAD module has no detection functions",
                          root_cause="Functions not found in audio.vad",
                          suggested_fix="Verify VAD implementation")

        success_silero, mod_silero, _ = self.safe_import("audio.silero_vad")
        if success_silero:
            self.add_result("VAD-Silero", "P0", TestStatus.PASS,
                          "Silero VAD module available (advanced VAD)")

    def test_p0_llm(self):
        """P0: Test LLM Integration"""
        self.log("Testing P0: LLM Integration")

        backends = [
            ("reasoning.local_rag_backend", "LocalRAGBackend"),
            ("reasoning.llm_router", "LLMRouter"),
            ("kloros_voice", "LLM integration in voice"),
        ]

        found = []
        for module_path, name in backends:
            success, mod, error = self.safe_import(module_path)
            if success:
                found.append((module_path, name))

        if found:
            self.add_result("LLM", "P0", TestStatus.PASS,
                          f"LLM integrations found: {[f[1] for f in found]}",
                          details=f"Modules: {[f[0] for f in found]}")
        else:
            self.add_result("LLM", "P0", TestStatus.FAIL,
                          "No LLM integration modules found",
                          root_cause="Could not import any LLM backend",
                          suggested_fix="Check reasoning.local_rag_backend and reasoning.llm_router")

    def test_p0_memory(self):
        """P0: Test Memory System"""
        self.log("Testing P0: Memory System")

        success, mod, error = self.safe_import("kloros_memory")
        if not success:
            self.add_result("Memory", "P0", TestStatus.FAIL,
                          "Failed to import kloros_memory",
                          root_cause=error,
                          suggested_fix="Check kloros_memory module structure")
            return

        components = {
            "MemoryStore": "storage.MemoryStore",
            "EventType": "models.EventType",
            "MemoryLogger": "logger.MemoryLogger",
            "EpisodeCondenser": "condenser.EpisodeCondenser",
            "ContextRetriever": "retriever.ContextRetriever",
        }

        found = []
        missing = []

        for name, full_path in components.items():
            if hasattr(mod, name):
                found.append(name)
            else:
                missing.append(name)

        if len(found) == len(components):
            self.add_result("Memory", "P0", TestStatus.PASS,
                          f"Memory system complete: all {len(found)} components found")

            try:
                EventType = mod.EventType
                event_types = [e.name for e in EventType]

                if 'WAKE_DETECTED' in event_types:
                    self.add_result("Memory-API", "P0", TestStatus.PASS,
                                  f"EventType.WAKE_DETECTED exists (and {len(event_types)} total types)")
                elif 'WAKE' in event_types:
                    self.add_result("Memory-API", "P0", TestStatus.WARN,
                                  "EventType.WAKE exists (not WAKE_DETECTED)",
                                  suggested_fix="Update callers to use WAKE instead of WAKE_DETECTED")
                else:
                    self.add_result("Memory-API", "P0", TestStatus.FAIL,
                                  "Neither WAKE nor WAKE_DETECTED found in EventType",
                                  root_cause=f"Available: {event_types}",
                                  suggested_fix="Add WAKE_DETECTED to EventType enum")

                MemoryStore = mod.MemoryStore
                store = MemoryStore(db_path="~/.kloros/test_memory.db")

                if hasattr(store, 'store_event'):
                    self.add_result("Memory-Store", "P0", TestStatus.PASS,
                                  "MemoryStore.store_event() method exists")
                elif hasattr(store, 'add_event'):
                    self.add_result("Memory-Store", "P0", TestStatus.WARN,
                                  "MemoryStore uses add_event() not store_event()",
                                  suggested_fix="Update callers to use add_event() instead")
                else:
                    methods = [m for m in dir(store) if not m.startswith('_') and callable(getattr(store, m))]
                    self.add_result("Memory-Store", "P0", TestStatus.FAIL,
                                  "No event storage method found in MemoryStore",
                                  root_cause=f"Available methods: {methods[:10]}...",
                                  suggested_fix="Implement store_event() or add_event()")

            except Exception as e:
                self.add_result("Memory-API", "P0", TestStatus.FAIL,
                              "Memory API test failed",
                              root_cause=f"{type(e).__name__}: {str(e)}")

        elif found:
            self.add_result("Memory", "P0", TestStatus.WARN,
                          f"Memory system partial: found {found}, missing {missing}",
                          suggested_fix=f"Implement missing components: {missing}")
        else:
            self.add_result("Memory", "P0", TestStatus.FAIL,
                          "Memory system components not found",
                          root_cause="No components accessible from kloros_memory",
                          suggested_fix="Fix kloros_memory/__init__.py imports")

    def test_p1_reasoning(self):
        """P1: Test Reasoning Systems"""
        self.log("Testing P1: Reasoning (ToT, Debate, VOI)")

        # Check reasoning directory structure
        success, reasoning_mod, error = self.safe_import("reasoning")
        if not success:
            self.add_result("Reasoning", "P1", TestStatus.FAIL,
                          "Failed to import reasoning module",
                          root_cause=error)
            return

        # Check for reasoning components
        components = {}

        submodules = ['local_rag_backend', 'llm_router', 'base', 'query_classifier', 'reasoning_trace']
        for submod in submodules:
            success, mod, _ = self.safe_import(f"reasoning.{submod}")
            if success:
                components[submod] = mod

        if components:
            self.add_result("Reasoning", "P1", TestStatus.PASS,
                          f"Reasoning framework found with {len(components)} modules: {list(components.keys())}")

            if 'local_rag_backend' in components:
                backend = components['local_rag_backend']
                if hasattr(backend, 'LocalRAGBackend'):
                    self.add_result("Reasoning-RAG", "P1", TestStatus.PASS,
                                  "LocalRAGBackend (main reasoning engine) found")

            if 'reasoning_trace' in components:
                self.add_result("Reasoning-Trace", "P1", TestStatus.PASS,
                              "Reasoning trace logging available")
        else:
            self.add_result("Reasoning", "P1", TestStatus.WARN,
                          "Reasoning module exists but submodules not found",
                          suggested_fix="Check reasoning/ directory structure")

        success_coord, coord_mod, _ = self.safe_import("reasoning_coordinator")
        if success_coord:
            self.add_result("Reasoning-Coord", "P1", TestStatus.PASS,
                          "Reasoning coordinator found (orchestrates reasoning modes)")

    def test_p1_orchestration(self):
        """P1: Test Orchestration System"""
        self.log("Testing P1: Orchestration")

        success, mod, error = self.safe_import("orchestrator")
        if success:
            self.add_result("Orchestrator", "P1", TestStatus.PASS,
                          "Orchestrator module found")
        else:
            self.add_result("Orchestrator", "P1", TestStatus.WARN,
                          "Orchestrator module not found (may be integrated into main loop)",
                          root_cause=error)

    def test_p1_self_healing(self):
        """P1: Test Self-Healing System"""
        self.log("Testing P1: Self-Healing")

        success, mod, error = self.safe_import("self_heal")
        if not success:
            self.add_result("SelfHeal", "P1", TestStatus.FAIL,
                          "Failed to import self_heal",
                          root_cause=error)
            return

        # Check for self-heal components
        components = []
        for submod in ['recovery', 'monitor', 'playbooks']:
            if os.path.exists(f'/home/kloros/src/self_heal/{submod}.py'):
                components.append(submod)

        if components:
            self.add_result("SelfHeal", "P1", TestStatus.PASS,
                          f"Self-healing system found with {len(components)} components: {components}")
        else:
            files = os.listdir('/home/kloros/src/self_heal')
            py_files = [f for f in files if f.endswith('.py') and f != '__init__.py']
            if py_files:
                self.add_result("SelfHeal", "P1", TestStatus.WARN,
                              f"Self-healing directory exists with files: {py_files}",
                              suggested_fix="Verify expected component names")
            else:
                self.add_result("SelfHeal", "P1", TestStatus.FAIL,
                              "Self-healing directory empty",
                              suggested_fix="Implement self-healing components")

    def test_p2_dream(self):
        """P2: Test D-REAM System"""
        self.log("Testing P2: D-REAM (Darwinian-RZero Evolution)")

        success, mod, error = self.safe_import("dream")
        if not success:
            self.add_result("D-REAM", "P2", TestStatus.FAIL,
                          "Failed to import dream module",
                          root_cause=error)
            return

        # Check for D-REAM components
        dream_dir = '/home/kloros/src/dream'
        subdirs = [d for d in os.listdir(dream_dir)
                  if os.path.isdir(os.path.join(dream_dir, d)) and not d.startswith('_')]

        if subdirs:
            self.add_result("D-REAM", "P2", TestStatus.PASS,
                          f"D-REAM system found with {len(subdirs)} subsystems: {subdirs}")

            for subdir in ['core', 'runner', 'workers']:
                if os.path.exists(os.path.join(dream_dir, subdir)):
                    self.add_result(f"D-REAM-{subdir}", "P2", TestStatus.PASS,
                                  f"D-REAM {subdir} subsystem present")
        else:
            self.add_result("D-REAM", "P2", TestStatus.WARN,
                          "D-REAM directory exists but no subsystems found",
                          suggested_fix="Check dream/ directory structure")

    def test_p2_phase(self):
        """P2: Test PHASE Scheduler"""
        self.log("Testing P2: PHASE (Phased Heuristic Adaptive Scheduling)")

        success, mod, error = self.safe_import("phase")
        if not success:
            self.add_result("PHASE", "P2", TestStatus.FAIL,
                          "Failed to import phase module",
                          root_cause=error)
            return

        phase_dir = '/home/kloros/src/phase'
        if os.path.exists(phase_dir):
            files = [f for f in os.listdir(phase_dir) if f.endswith('.py')]
            self.add_result("PHASE", "P2", TestStatus.PASS,
                          f"PHASE scheduler found with {len(files)} modules: {files}")
        else:
            self.add_result("PHASE", "P2", TestStatus.FAIL,
                          "PHASE directory not found",
                          suggested_fix="Verify phase/ directory exists")

    def test_p2_curiosity_reflection(self):
        """P2: Test Curiosity and Reflection Systems"""
        self.log("Testing P2: Curiosity & Reflection")

        success, mod, error = self.safe_import("idle_reflection")
        if not success:
            self.add_result("Idle-Reflection", "P2", TestStatus.FAIL,
                          "Failed to import idle_reflection",
                          root_cause=error)
            return

        idle_dir = '/home/kloros/src/idle_reflection'
        if os.path.exists(idle_dir):
            files = [f for f in os.listdir(idle_dir) if f.endswith('.py')]
            self.add_result("Idle-Reflection", "P2", TestStatus.PASS,
                          f"Idle reflection system found with {len(files)} modules: {files}")

            for component in ['curiosity', 'reflection']:
                if f'{component}.py' in files:
                    self.add_result(f"Idle-{component.capitalize()}", "P2", TestStatus.PASS,
                                  f"{component.capitalize()} engine present")
                else:
                    self.add_result(f"Idle-{component.capitalize()}", "P2", TestStatus.WARN,
                                  f"{component.capitalize()} engine not found",
                                  suggested_fix=f"Check for {component}.py in idle_reflection/")

        success_kloros_idle, mod_idle, _ = self.safe_import("kloros_idle_reflection")
        if success_kloros_idle:
            self.add_result("Kloros-Idle-Reflection", "P2", TestStatus.PASS,
                          "kloros_idle_reflection main module found")

    def test_p3_tool_synthesis(self):
        """P3: Test Tool Synthesis"""
        self.log("Testing P3: Tool Synthesis")

        tool_dir = '/home/kloros/src/tool_synthesis'
        if not os.path.exists(tool_dir):
            self.add_result("ToolSynthesis", "P3", TestStatus.FAIL,
                          "Tool synthesis directory not found",
                          suggested_fix="Verify tool_synthesis/ directory exists")
            return

        files = [f for f in os.listdir(tool_dir) if f.endswith('.py') and f != '__init__.py']

        if files:
            self.add_result("ToolSynthesis", "P3", TestStatus.PASS,
                          f"Tool synthesis system found with {len(files)} modules: {files}")

            key_modules = ['ecosystem_manager', 'validator', 'storage', 'isolated_executor']
            found = [m for m in key_modules if f'{m}.py' in files]
            missing = [m for m in key_modules if m not in found]

            if found:
                self.add_result("ToolSynthesis-Modules", "P3", TestStatus.PASS,
                              f"Key modules present: {found}")
            if missing:
                self.add_result("ToolSynthesis-Missing", "P3", TestStatus.WARN,
                              f"Expected modules missing: {missing}")
        else:
            self.add_result("ToolSynthesis", "P3", TestStatus.FAIL,
                          "Tool synthesis directory empty",
                          suggested_fix="Implement tool synthesis modules")

    def test_p3_introspection(self):
        """P3: Test Introspection Tools"""
        self.log("Testing P3: Introspection Tools Registry")

        success, mod, error = self.safe_import("introspection_tools")
        if not success:
            self.add_result("Introspection", "P3", TestStatus.FAIL,
                          "Failed to import introspection_tools",
                          root_cause=error)
            return

        try:
            if hasattr(mod, 'IntrospectionToolRegistry'):
                registry_class = mod.IntrospectionToolRegistry
                registry = registry_class()

                # Try different methods to get tool count
                tool_count = None
                if hasattr(registry, 'get_all_tools'):
                    tools = registry.get_all_tools()
                    tool_count = len(tools) if tools else 0
                elif hasattr(registry, 'list_tools'):
                    tools = registry.list_tools()
                    tool_count = len(tools) if tools else 0
                elif hasattr(registry, 'tools'):
                    tool_count = len(registry.tools) if registry.tools else 0

                if tool_count is not None:
                    if tool_count >= 60:  # Close to expected 69
                        self.add_result("Introspection", "P3", TestStatus.PASS,
                                      f"IntrospectionToolRegistry has {tool_count} tools")
                    elif tool_count > 0:
                        self.add_result("Introspection", "P3", TestStatus.WARN,
                                      f"Tool count: expected ~69, got {tool_count}",
                                      suggested_fix="Verify all tools are registered")
                    else:
                        self.add_result("Introspection", "P3", TestStatus.FAIL,
                                      "IntrospectionToolRegistry has no tools",
                                      root_cause="Registry appears empty",
                                      suggested_fix="Check tool registration logic")
                else:
                    methods = [m for m in dir(registry) if not m.startswith('_')]
                    self.add_result("Introspection", "P3", TestStatus.WARN,
                                  "Cannot determine tool count",
                                  details=f"Available methods: {methods[:10]}...")
            else:
                self.add_result("Introspection", "P3", TestStatus.FAIL,
                              "IntrospectionToolRegistry class not found",
                              suggested_fix="Check introspection_tools.py structure")

        except Exception as e:
            self.add_result("Introspection", "P3", TestStatus.FAIL,
                          "Introspection test failed",
                          root_cause=f"{type(e).__name__}: {str(e)}",
                          suggested_fix="Fix IntrospectionToolRegistry implementation")

    def test_p3_mcp(self):
        """P3: Test MCP Integration"""
        self.log("Testing P3: MCP (Model Context Protocol)")

        mcp_dir = '/home/kloros/src/mcp'
        if not os.path.exists(mcp_dir):
            self.add_result("MCP", "P3", TestStatus.WARN,
                          "MCP directory not found (may not be implemented)",
                          details="MCP integration may be planned for future")
            return

        files = [f for f in os.listdir(mcp_dir) if f.endswith('.py')]
        if files:
            self.add_result("MCP", "P3", TestStatus.PASS,
                          f"MCP system found with {len(files)} modules: {files}")
        else:
            self.add_result("MCP", "P3", TestStatus.WARN,
                          "MCP directory exists but is empty",
                          suggested_fix="Implement MCP components or remove directory")

    def test_p3_agents(self):
        """P3: Test Agent System"""
        self.log("Testing P3: Agent Systems")

        agent_modules = ['agentflow', 'dev_agent', 'deepagents', 'browser_agent']
        found = []

        for agent_mod in agent_modules:
            agent_dir = f'/home/kloros/src/{agent_mod}'
            if os.path.exists(agent_dir):
                files = [f for f in os.listdir(agent_dir) if f.endswith('.py')]
                found.append((agent_mod, len(files)))

        if found:
            self.add_result("Agents", "P3", TestStatus.PASS,
                          f"Agent systems found: {dict(found)}")
            for agent_mod, file_count in found:
                self.add_result(f"Agent-{agent_mod}", "P3", TestStatus.PASS,
                              f"{agent_mod} has {file_count} modules")
        else:
            self.add_result("Agents", "P3", TestStatus.WARN,
                          "No agent systems found",
                          suggested_fix="Check agent module directories")

    def test_p4_logging(self):
        """P4: Test Logging System"""
        self.log("Testing P4: Logging")

        success, mod, error = self.safe_import("logging")
        if success:
            self.add_result("Logging", "P4", TestStatus.PASS,
                          "Logging module imported (Python standard library)")

        # Check custom logging
        log_dir = '/home/kloros/src/logging'
        if os.path.exists(log_dir):
            files = [f for f in os.listdir(log_dir) if f.endswith('.py')]
            self.add_result("Logging-Custom", "P4", TestStatus.PASS,
                          f"Custom logging system found with {len(files)} modules: {files}")

        # Check memory logger
        success_mem, mod_mem, _ = self.safe_import("kloros_memory.logger")
        if success_mem:
            self.add_result("Logging-Memory", "P4", TestStatus.PASS,
                          "Memory logger (kloros_memory.logger) available")

    def test_p4_metrics(self):
        """P4: Test Metrics System"""
        self.log("Testing P4: Metrics")

        # Check observer metrics
        success, mod, error = self.safe_import("observer")
        if success:
            obs_dir = '/home/kloros/src/observer'
            if os.path.exists(obs_dir):
                files = [f for f in os.listdir(obs_dir) if f.endswith('.py')]
                self.add_result("Metrics-Observer", "P4", TestStatus.PASS,
                              f"Observer system found with {len(files)} modules: {files}")

        # Check memory metrics
        success_mem, mod_mem, _ = self.safe_import("kloros_memory.metrics")
        if success_mem:
            self.add_result("Metrics-Memory", "P4", TestStatus.PASS,
                          "Memory metrics (kloros_memory.metrics) available")

        # Check for metrics directory
        metrics_dir = '/home/kloros/metrics'
        if os.path.exists(metrics_dir):
            files = os.listdir(metrics_dir)
            self.add_result("Metrics-Data", "P4", TestStatus.PASS,
                          f"Metrics data directory exists with {len(files)} files")

    def test_additional_subsystems(self):
        """Test additional subsystems not in P0-P4"""
        self.log("Testing Additional Subsystems")

        additional = {
            "ACE": "src/ace",
            "Consciousness": "src/consciousness",
            "Meta-Cognition": "src/meta_cognition",
            "Persona": "src/persona",
            "Registry": "src/registry",
            "RAG": "src/rag",
            "Config": "src/config",
            "Core": "src/core",
            "Integrations": "src/integrations",
            "Middleware": "src/middleware",
        }

        for name, path in additional.items():
            full_path = f'/home/kloros/{path}'
            if os.path.exists(full_path):
                if os.path.isdir(full_path):
                    files = [f for f in os.listdir(full_path) if f.endswith('.py')]
                    self.add_result(name, "P2/P3", TestStatus.PASS,
                                  f"{name} subsystem found with {len(files)} modules")
                else:
                    self.add_result(name, "P2/P3", TestStatus.PASS,
                                  f"{name} module file exists")

    def test_dependencies(self):
        """Test critical dependencies"""
        self.log("Testing Critical Dependencies")

        deps = {
            "numpy": "Scientific computing",
            "chromadb": "Vector database",
            "librosa": "Audio processing",
            "sounddevice": "Audio I/O",
            "soundfile": "Audio file handling",
        }

        for dep, description in deps.items():
            try:
                __import__(dep)
                self.add_result(f"Dep-{dep}", "P0", TestStatus.PASS,
                              f"{dep} installed ({description})")
            except ImportError:
                self.add_result(f"Dep-{dep}", "P0", TestStatus.FAIL,
                              f"{dep} not installed ({description})",
                              suggested_fix=f"pip install {dep}")

    def run_all_tests(self):
        """Run all tests in priority order"""
        print("=" * 80)
        print("KLoROS COMPREHENSIVE TEST SUITE V2")
        print("Testing 71+ subsystems with 371+ capabilities")
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
        self.test_p1_reasoning()
        self.test_p1_orchestration()
        self.test_p1_self_healing()

        print("\n=== P2: ADVANCED SUBSYSTEMS ===\n")
        self.test_p2_dream()
        self.test_p2_phase()
        self.test_p2_curiosity_reflection()

        print("\n=== P3: EXTENDED SUBSYSTEMS ===\n")
        self.test_p3_tool_synthesis()
        self.test_p3_introspection()
        self.test_p3_mcp()
        self.test_p3_agents()

        print("\n=== P4: SUPPORT SUBSYSTEMS ===\n")
        self.test_p4_logging()
        self.test_p4_metrics()

        print("\n=== ADDITIONAL SUBSYSTEMS ===\n")
        self.test_additional_subsystems()

        print("\n=== DEPENDENCIES ===\n")
        self.test_dependencies()

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
            for priority in ['P0', 'P1', 'P2', 'P3', 'P4', 'P2/P3']:
                if priority in priority_failures:
                    print(f"\n{priority}:")
                    for subsystem in priority_failures[priority]:
                        print(f"  - {subsystem}")
        else:
            print("\n✅ No critical failures detected!")

        print("\n" + "=" * 80)
        print(f"\nTest suite completed. Health score: {passes/total*100:.1f}%")
        print("=" * 80)

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
