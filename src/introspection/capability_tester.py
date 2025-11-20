"""Capability testing framework for KLoROS self-optimization.

Tests and benchmarks all capabilities to feed metrics into D-REAM
for evolutionary optimization.
"""

import os
import time
import tempfile
import subprocess
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime


class CapabilityTester:
    """Tests KLoROS capabilities and generates optimization metrics."""

    def __init__(self, kloros_instance=None):
        self.kloros_instance = kloros_instance
        self.test_results: Dict[str, Any] = {}
        self.test_root = Path("/home/kloros/.kloros/capability_tests")
        self.test_root.mkdir(parents=True, exist_ok=True)

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all capability tests.

        Returns:
            Dictionary of test results with metrics
        """
        print("[capability_tester] Starting comprehensive capability tests...")
        start = datetime.now()

        self.test_results = {
            "timestamp": datetime.now().isoformat(),
            "stt": self._test_stt(),
            "tts": self._test_tts(),
            "rag": self._test_rag(),
            "vad": self._test_vad(),
            "tool_execution": self._test_tool_execution(),
            "memory": self._test_memory(),
        }

        # Calculate overall health score
        self.test_results["health_score"] = self._calculate_health_score()

        duration = (datetime.now() - start).total_seconds()
        self.test_results["test_duration_s"] = duration

        print(f"[capability_tester] Tests completed in {duration:.1f}s")
        print(f"[capability_tester] Overall health score: {self.test_results['health_score']:.2f}/1.0")

        # Save results for D-REAM
        self._save_results()

        return self.test_results

    def _test_stt(self) -> Dict[str, Any]:
        """Test STT accuracy and performance."""
        print("[capability_tester] Testing STT...")

        if not self.kloros_instance or not hasattr(self.kloros_instance, 'stt_backend'):
            return {"available": False, "reason": "STT backend not initialized"}

        results = {
            "available": True,
            "backend": getattr(self.kloros_instance, 'stt_backend_name', 'unknown'),
            "tests": []
        }

        # Test phrases with known ground truth
        test_phrases = [
            "hello world",
            "what is the weather today",
            "system diagnostic",
            "tell me about your capabilities",
        ]

        # For testing, we'd need reference audio files
        # For now, just check if STT is responsive
        try:
            # Create silent audio to verify STT doesn't crash
            silent_audio = np.zeros(44100, dtype=np.float32)  # 1 second of silence
            start = time.time()
            result = self.kloros_instance.stt_backend.transcribe(silent_audio, sample_rate=44100)
            latency = time.time() - start

            results["tests"].append({
                "test": "silent_audio_handling",
                "passed": True,
                "latency_ms": latency * 1000,
                "output": result.transcript if hasattr(result, 'transcript') else str(result)
            })

            results["responsive"] = True
            results["average_latency_ms"] = latency * 1000

        except Exception as e:
            results["tests"].append({
                "test": "silent_audio_handling",
                "passed": False,
                "error": str(e)
            })
            results["responsive"] = False

        return results

    def _test_tts(self) -> Dict[str, Any]:
        """Test TTS quality and performance."""
        print("[capability_tester] Testing TTS...")

        if not self.kloros_instance or not hasattr(self.kloros_instance, 'tts_backend'):
            return {"available": False, "reason": "TTS backend not initialized"}

        results = {
            "available": True,
            "backend": getattr(self.kloros_instance, 'tts_backend_name', 'unknown'),
            "tests": []
        }

        # Test synthesis speed and quality
        test_phrases = [
            "Hello.",
            "The quick brown fox jumps over the lazy dog.",
            "This is a longer sentence to test synthesis speed and quality.",
        ]

        total_chars = 0
        total_time = 0

        for phrase in test_phrases:
            try:
                start = time.time()
                result = self.kloros_instance.tts_backend.synthesize(phrase, sample_rate=22050)
                synthesis_time = time.time() - start

                total_chars += len(phrase)
                total_time += synthesis_time

                # Check if audio file was created
                audio_exists = hasattr(result, 'audio_path') and Path(result.audio_path).exists()

                results["tests"].append({
                    "phrase": phrase,
                    "passed": audio_exists,
                    "synthesis_time_ms": synthesis_time * 1000,
                    "chars_per_second": len(phrase) / synthesis_time if synthesis_time > 0 else 0
                })

            except Exception as e:
                results["tests"].append({
                    "phrase": phrase,
                    "passed": False,
                    "error": str(e)
                })

        if total_time > 0:
            results["average_chars_per_second"] = total_chars / total_time
            results["responsive"] = True
        else:
            results["responsive"] = False

        return results

    def _test_rag(self) -> Dict[str, Any]:
        """Test RAG retrieval accuracy and relevance."""
        print("[capability_tester] Testing RAG...")

        if not self.kloros_instance or not hasattr(self.kloros_instance, 'reason_backend'):
            return {"available": False, "reason": "RAG backend not initialized"}

        results = {
            "available": True,
            "backend": getattr(self.kloros_instance, 'reason_backend_name', 'unknown'),
            "tests": []
        }

        # Test queries with expected knowledge
        test_queries = [
            ("What is KLoROS?", ["kloros", "voice", "assistant"]),
            ("How does RAG work?", ["rag", "retrieval", "document"]),
            ("What tools are available?", ["tool", "introspection"]),
        ]

        for query, expected_keywords in test_queries:
            try:
                start = time.time()
                result = self.kloros_instance.reason_backend.reply(query, kloros_instance=self.kloros_instance)
                retrieval_time = time.time() - start

                response = result.reply_text if hasattr(result, 'reply_text') else str(result)
                sources = result.sources if hasattr(result, 'sources') else []

                # Check if expected keywords appear in response (case-insensitive)
                response_lower = response.lower()
                keywords_found = [kw for kw in expected_keywords if kw.lower() in response_lower]
                relevance_score = len(keywords_found) / len(expected_keywords) if expected_keywords else 0

                results["tests"].append({
                    "query": query,
                    "passed": relevance_score > 0.5,
                    "retrieval_time_ms": retrieval_time * 1000,
                    "relevance_score": relevance_score,
                    "sources_retrieved": len(sources),
                    "keywords_found": keywords_found
                })

            except Exception as e:
                results["tests"].append({
                    "query": query,
                    "passed": False,
                    "error": str(e)
                })

        # Calculate average metrics
        passed_tests = [t for t in results["tests"] if t.get("passed")]
        if passed_tests:
            results["average_retrieval_time_ms"] = np.mean([t["retrieval_time_ms"] for t in passed_tests])
            results["average_relevance"] = np.mean([t["relevance_score"] for t in passed_tests])

        return results

    def _test_vad(self) -> Dict[str, Any]:
        """Test VAD sensitivity and accuracy."""
        print("[capability_tester] Testing VAD...")

        results = {
            "available": True,
            "tests": []
        }

        # Test VAD with synthetic audio
        try:
            from src.audio.vad import detect_voiced_segments

            # Test 1: Silent audio should have no segments
            silent_audio = np.zeros(44100, dtype=np.float32)
            segments, metrics = detect_voiced_segments(
                silent_audio,
                sample_rate=44100,
                threshold_dbfs=-28.0,
                frame_ms=30,
                hop_ms=10
            )

            results["tests"].append({
                "test": "silence_rejection",
                "passed": len(segments) == 0,
                "segments_detected": len(segments)
            })

            # Test 2: Loud audio should detect segments
            loud_audio = np.random.normal(0, 0.5, 44100).astype(np.float32)
            segments, metrics = detect_voiced_segments(
                loud_audio,
                sample_rate=44100,
                threshold_dbfs=-28.0,
                frame_ms=30,
                hop_ms=10
            )

            results["tests"].append({
                "test": "voice_detection",
                "passed": len(segments) > 0,
                "segments_detected": len(segments)
            })

        except Exception as e:
            results["tests"].append({
                "test": "vad_general",
                "passed": False,
                "error": str(e)
            })

        return results

    def _test_tool_execution(self) -> Dict[str, Any]:
        """Test tool registry and execution."""
        print("[capability_tester] Testing tool execution...")

        results = {
            "available": True,
            "tests": []
        }

        try:
            from src.introspection_tools import IntrospectionToolRegistry
            registry = IntrospectionToolRegistry()

            # Test a few safe tools
            safe_tools = ["component_status", "check_dependencies"]

            for tool_name in safe_tools:
                if tool_name in registry.tools:
                    try:
                        start = time.time()
                        result = registry.tools[tool_name].func(self.kloros_instance)
                        execution_time = time.time() - start

                        results["tests"].append({
                            "tool": tool_name,
                            "passed": True,
                            "execution_time_ms": execution_time * 1000,
                            "output_length": len(str(result))
                        })

                    except Exception as e:
                        results["tests"].append({
                            "tool": tool_name,
                            "passed": False,
                            "error": str(e)
                        })

            results["tool_count"] = len(registry.tools)

        except Exception as e:
            results["available"] = False
            results["error"] = str(e)

        return results

    def _test_memory(self) -> Dict[str, Any]:
        """Test memory system."""
        print("[capability_tester] Testing memory system...")

        results = {
            "available": False,
            "tests": []
        }

        if not self.kloros_instance or not hasattr(self.kloros_instance, 'memory_enhanced'):
            return results

        try:
            memory_system = self.kloros_instance.memory_enhanced
            if memory_system and hasattr(memory_system, 'memory_logger'):
                results["available"] = True

                # Test memory storage
                test_transcript = "Test query for memory system"
                try:
                    memory_system.memory_logger.log_user_input(test_transcript, confidence=1.0)
                    results["tests"].append({
                        "test": "user_input_logging",
                        "passed": True
                    })
                except Exception as e:
                    results["tests"].append({
                        "test": "user_input_logging",
                        "passed": False,
                        "error": str(e)
                    })

                # Test memory retrieval
                try:
                    memories = memory_system.memory_logger.retrieve_recent_context(limit=5)
                    results["tests"].append({
                        "test": "context_retrieval",
                        "passed": True,
                        "memories_retrieved": len(memories)
                    })
                except Exception as e:
                    results["tests"].append({
                        "test": "context_retrieval",
                        "passed": False,
                        "error": str(e)
                    })

        except Exception as e:
            results["error"] = str(e)

        return results

    def _calculate_health_score(self) -> float:
        """Calculate overall system health score (0-1)."""
        scores = []

        for component, test_data in self.test_results.items():
            if component in ["timestamp", "test_duration_s", "health_score"]:
                continue

            if not isinstance(test_data, dict):
                continue

            # Check if component is available
            if not test_data.get("available", False):
                scores.append(0.0)
                continue

            # Calculate pass rate for tests
            tests = test_data.get("tests", [])
            if tests:
                passed = sum(1 for t in tests if t.get("passed", False))
                pass_rate = passed / len(tests)
                scores.append(pass_rate)
            else:
                # If responsive but no tests, assume working
                if test_data.get("responsive"):
                    scores.append(0.8)
                else:
                    scores.append(0.5)

        return np.mean(scores) if scores else 0.0

    def _save_results(self):
        """Save test results for D-REAM analysis."""
        import json

        results_file = self.test_root / f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            with open(results_file, 'w') as f:
                json.dump(self.test_results, f, indent=2)
            print(f"[capability_tester] Results saved to {results_file}")
        except Exception as e:
            print(f"[capability_tester] Failed to save results: {e}")

    def get_optimization_targets(self) -> List[Dict[str, Any]]:
        """Identify components that need optimization.

        Returns:
            List of optimization targets for D-REAM
        """
        if not self.test_results:
            return []

        targets = []

        for component, test_data in self.test_results.items():
            if component in ["timestamp", "test_duration_s", "health_score"]:
                continue

            if not isinstance(test_data, dict):
                continue

            # Check for failures
            tests = test_data.get("tests", [])
            failed_tests = [t for t in tests if not t.get("passed", False)]

            if failed_tests:
                targets.append({
                    "component": component,
                    "priority": "high",
                    "reason": f"{len(failed_tests)}/{len(tests)} tests failed",
                    "failed_tests": [t.get("test", "unknown") for t in failed_tests]
                })

            # Check for performance issues
            if component == "stt" and test_data.get("average_latency_ms", 0) > 200:
                targets.append({
                    "component": "stt",
                    "priority": "medium",
                    "reason": f"High latency: {test_data['average_latency_ms']:.0f}ms",
                    "metric": "latency"
                })

            if component == "rag" and test_data.get("average_relevance", 1.0) < 0.7:
                targets.append({
                    "component": "rag",
                    "priority": "high",
                    "reason": f"Low relevance: {test_data['average_relevance']:.2f}",
                    "metric": "relevance"
                })

        return targets

    def submit_to_dream(self):
        """Submit test results to D-REAM for evolutionary optimization."""
        print("[capability_tester] Submitting results to D-REAM...")

        targets = self.get_optimization_targets()

        if not targets:
            print("[capability_tester] No optimization targets identified")
            return

        # Try to submit to D-REAM
        try:
            from src.evolution.dream import DreamEvolutionManager

            dream = DreamEvolutionManager(kloros_instance=self.kloros_instance)

            for target in targets:
                # Create improvement task for D-REAM
                task_description = f"Optimize {target['component']}: {target['reason']}"

                print(f"[capability_tester] Submitting task to D-REAM: {task_description}")

                # D-REAM would need a method to accept optimization tasks
                # For now, just log it
                print(f"[capability_tester] → Component: {target['component']}")
                print(f"[capability_tester] → Priority: {target['priority']}")
                print(f"[capability_tester] → Reason: {target['reason']}")

        except Exception as e:
            print(f"[capability_tester] D-REAM submission failed: {e}")
