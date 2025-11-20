#!/usr/bin/env python3
"""
Real Evolutionary Integration System for KLoROS D-REAM
Integrates with actual KLoROS components without mocking.
"""

import os
import sys
import time
import json
import importlib
import tempfile
import traceback
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

# Add KLoROS src to path for real component access
sys.path.insert(0, '/home/kloros/src')

@dataclass
class RealTestResult:
    """Results from testing with real KLoROS components."""
    approach_id: str
    success: bool
    performance_score: float
    response_time: float
    error_message: Optional[str] = None
    empirical_data: Optional[Dict[str, Any]] = None

class RealEvolutionaryIntegrator:
    """Real evolutionary integration that works with live KLoROS components."""

    def __init__(self):
        """Initialize real integrator with KLoROS component access."""
        self.work_dir = Path("/home/kloros/.kloros/real_evolution")
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Initialize real KLoROS components
        self._init_real_components()

    def _init_real_components(self):
        """Initialize real KLoROS components for testing."""
        try:
            # Import real KLoROS components
            from kloros_voice import KLoROS
            from reasoning.local_rag_backend import LocalRagBackend
            from src.kloros_memory.integration import MemoryEnhancedKLoROS

            # Create real KLoROS instance
            self.kloros_instance = KLoROS()

            # Initialize memory enhancement if available
            if hasattr(self.kloros_instance, 'memory_enhanced') and self.kloros_instance.memory_enhanced:
                self.memory_enhanced = self.kloros_instance.memory_enhanced
            else:
                # Create memory enhancement if not present
                self.memory_enhanced = MemoryEnhancedKLoROS(self.kloros_instance)
                self.kloros_instance.memory_enhanced = self.memory_enhanced

            # Get real reasoning backend
            self.reasoning_backend = self.kloros_instance.reason_backend

            print("[real_evolution] Initialized real KLoROS components successfully")

        except Exception as e:
            print(f"[real_evolution] Failed to initialize real components: {e}")
            traceback.print_exc()
            raise

    def test_memory_integration_approach(self, approach_code: str, test_cases: List[Dict[str, Any]]) -> RealTestResult:
        """Test memory integration approach with real KLoROS memory system."""
        start_time = time.time()

        try:
            # Create temporary module with approach code
            approach_module = self._create_temp_module(approach_code, "memory_integration_real")

            # Test with real memory enhanced KLoROS
            total_score = 0.0
            successful_tests = 0
            empirical_results = []

            for test_case in test_cases:
                input_text = test_case.get("input", "")
                expect_context = test_case.get("expect_context", False)

                try:
                    # Test the approach with real memory system
                    if hasattr(approach_module, "memory_enhanced_chat_wrapper"):
                        # Apply the evolutionary approach to real system
                        original_chat = self.kloros_instance.chat

                        # Temporarily patch with evolutionary approach
                        enhanced_chat = lambda msg: approach_module.memory_enhanced_chat_wrapper(self.kloros_instance, msg)

                        # Test the enhanced system
                        response = enhanced_chat(input_text)

                        # Restore original method
                        # (We don't permanently modify in testing phase)

                        # Evaluate the results
                        context_detected = self._analyze_context_usage(input_text, response)
                        context_success = (context_detected == expect_context)

                        test_score = 0.9 if context_success else 0.4
                        total_score += test_score
                        successful_tests += 1

                        empirical_results.append({
                            "input": input_text,
                            "response": response,
                            "context_detected": context_detected,
                            "expected_context": expect_context,
                            "success": context_success,
                            "score": test_score
                        })

                    else:
                        empirical_results.append({
                            "input": input_text,
                            "error": "Approach method not found",
                            "success": False,
                            "score": 0.0
                        })

                except Exception as test_error:
                    empirical_results.append({
                        "input": input_text,
                        "error": str(test_error),
                        "success": False,
                        "score": 0.0
                    })

            # Calculate final performance
            final_score = (total_score / len(test_cases)) if test_cases else 0.0
            response_time = time.time() - start_time

            # Cleanup
            self._cleanup_temp_module(approach_module)

            return RealTestResult(
                approach_id="memory_integration_real",
                success=successful_tests > 0,
                performance_score=final_score,
                response_time=response_time,
                empirical_data={
                    "successful_tests": successful_tests,
                    "total_tests": len(test_cases),
                    "test_results": empirical_results
                }
            )

        except Exception as e:
            return RealTestResult(
                approach_id="memory_integration_real",
                success=False,
                performance_score=0.0,
                response_time=time.time() - start_time,
                error_message=str(e),
                empirical_data={"error": traceback.format_exc()}
            )

    def test_llm_consistency_approach(self, approach_code: str, test_cases: List[Dict[str, Any]]) -> RealTestResult:
        """Test LLM consistency approach with real KLoROS reasoning backend."""
        start_time = time.time()

        try:
            # Create temporary module with approach code
            approach_module = self._create_temp_module(approach_code, "llm_consistency_real")

            # Test with real reasoning backend
            total_score = 0.0
            successful_tests = 0
            empirical_results = []

            for test_case in test_cases:
                input_text = test_case.get("input", "")
                expect_tool = test_case.get("expect_tool", "")

                try:
                    # Test the approach with real reasoning backend
                    if hasattr(approach_module, "apply_tool_template_constraints"):
                        # Get real LLM response for tool request
                        reasoning_result = self.reasoning_backend.reply(f"Create tool {input_text}", kloros_instance=self.kloros_instance)
                        original_response = reasoning_result.reply_text

                        # Apply evolutionary constraints
                        enhanced_response = approach_module.apply_tool_template_constraints(self.reasoning_backend, original_response)

                        # Evaluate consistency improvement
                        consistency_improved = self._evaluate_tool_consistency(original_response, enhanced_response, expect_tool)

                        test_score = 0.9 if consistency_improved else 0.5
                        total_score += test_score
                        successful_tests += 1

                        empirical_results.append({
                            "input": input_text,
                            "original_response": original_response,
                            "enhanced_response": enhanced_response,
                            "expected_tool": expect_tool,
                            "consistency_improved": consistency_improved,
                            "success": True,
                            "score": test_score
                        })

                    else:
                        empirical_results.append({
                            "input": input_text,
                            "error": "Approach method not found",
                            "success": False,
                            "score": 0.0
                        })

                except Exception as test_error:
                    empirical_results.append({
                        "input": input_text,
                        "error": str(test_error),
                        "success": False,
                        "score": 0.0
                    })

            # Calculate final performance
            final_score = (total_score / len(test_cases)) if test_cases else 0.0
            response_time = time.time() - start_time

            # Cleanup
            self._cleanup_temp_module(approach_module)

            return RealTestResult(
                approach_id="llm_consistency_real",
                success=successful_tests > 0,
                performance_score=final_score,
                response_time=response_time,
                empirical_data={
                    "successful_tests": successful_tests,
                    "total_tests": len(test_cases),
                    "test_results": empirical_results
                }
            )

        except Exception as e:
            return RealTestResult(
                approach_id="llm_consistency_real",
                success=False,
                performance_score=0.0,
                response_time=time.time() - start_time,
                error_message=str(e),
                empirical_data={"error": traceback.format_exc()}
            )

    def test_rag_quality_approach(self, approach_code: str, test_cases: List[Dict[str, Any]]) -> RealTestResult:
        """Test RAG quality approach with real KLoROS RAG system."""
        start_time = time.time()

        try:
            # Create temporary module with approach code
            approach_module = self._create_temp_module(approach_code, "rag_quality_real")

            # Test with real RAG backend
            total_score = 0.0
            successful_tests = 0
            empirical_results = []

            for test_case in test_cases:
                input_text = test_case.get("input", "")
                expect_improvement = test_case.get("expect_improvement", False)

                try:
                    # Test the approach with real RAG system
                    if hasattr(approach_module, "inject_tool_synthesis_examples"):
                        # Get real RAG retrieval
                        if hasattr(self.reasoning_backend, 'rag_instance') and self.reasoning_backend.rag_instance:
                            # Get real retrieved documents
                            embedder = self.reasoning_backend._get_embedder_function()
                            query_embedding = embedder(input_text)

                            # Get real retrieval results
                            original_docs = self.reasoning_backend.rag_instance.query(query_embedding, top_k=5)

                            # Apply evolutionary enhancement
                            enhanced_docs = approach_module.inject_tool_synthesis_examples(self.reasoning_backend, input_text, original_docs)

                            # Evaluate improvement
                            improvement_detected = self._evaluate_rag_improvement(original_docs, enhanced_docs, input_text)

                            test_score = 0.85 if improvement_detected else 0.6
                            total_score += test_score
                            successful_tests += 1

                            empirical_results.append({
                                "input": input_text,
                                "original_docs_count": len(original_docs),
                                "enhanced_docs_count": len(enhanced_docs),
                                "improvement_detected": improvement_detected,
                                "success": True,
                                "score": test_score
                            })
                        else:
                            empirical_results.append({
                                "input": input_text,
                                "error": "RAG instance not available",
                                "success": False,
                                "score": 0.0
                            })
                    else:
                        empirical_results.append({
                            "input": input_text,
                            "error": "Approach method not found",
                            "success": False,
                            "score": 0.0
                        })

                except Exception as test_error:
                    empirical_results.append({
                        "input": input_text,
                        "error": str(test_error),
                        "success": False,
                        "score": 0.0
                    })

            # Calculate final performance
            final_score = (total_score / len(test_cases)) if test_cases else 0.0
            response_time = time.time() - start_time

            # Cleanup
            self._cleanup_temp_module(approach_module)

            return RealTestResult(
                approach_id="rag_quality_real",
                success=successful_tests > 0,
                performance_score=final_score,
                response_time=response_time,
                empirical_data={
                    "successful_tests": successful_tests,
                    "total_tests": len(test_cases),
                    "test_results": empirical_results
                }
            )

        except Exception as e:
            return RealTestResult(
                approach_id="rag_quality_real",
                success=False,
                performance_score=0.0,
                response_time=time.time() - start_time,
                error_message=str(e),
                empirical_data={"error": traceback.format_exc()}
            )

    def _create_temp_module(self, code: str, module_name: str):
        """Create temporary module from evolutionary approach code."""
        # Create temporary file
        temp_file = self.work_dir / f"{module_name}_{int(time.time())}.py"

        # Write approach code
        with open(temp_file, 'w') as f:
            f.write("# Temporary evolutionary approach module\n")
            f.write("import sys\nimport os\nimport time\nfrom typing import List, Dict, Any\n\n")
            f.write(code)

        # Import module
        spec = importlib.util.spec_from_file_location(module_name, temp_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Store temp file path for cleanup
        module._temp_file_path = temp_file

        return module

    def _cleanup_temp_module(self, module):
        """Clean up temporary module and files."""
        try:
            if hasattr(module, '_temp_file_path'):
                temp_file = module._temp_file_path
                if temp_file.exists():
                    temp_file.unlink()
        except Exception as e:
            print(f"[real_evolution] Cleanup warning: {e}")

    def _analyze_context_usage(self, input_text: str, response: str) -> bool:
        """Analyze if memory context was actually used in the response."""
        # Look for indicators that memory context influenced the response
        context_indicators = [
            "previous", "earlier", "discussed", "mentioned", "context",
            "remember", "recall", "before", "last time", "we talked"
        ]

        # Check if response shows signs of contextual awareness
        response_lower = response.lower()
        return any(indicator in response_lower for indicator in context_indicators)

    def _evaluate_tool_consistency(self, original: str, enhanced: str, expected_tool: str) -> bool:
        """Evaluate if the enhanced response shows improved tool consistency."""
        # Check if enhanced version is more consistent with expected tool format
        if expected_tool:
            return expected_tool in enhanced and (expected_tool not in original or enhanced.count(expected_tool) > original.count(expected_tool))

        # Check for general consistency improvements
        tool_pattern = r"TOOL:\s*\w+"
        enhanced_tools = len(re.findall(tool_pattern, enhanced))
        original_tools = len(re.findall(tool_pattern, original))

        return enhanced_tools >= original_tools

    def _evaluate_rag_improvement(self, original_docs: List, enhanced_docs: List, query: str) -> bool:
        """Evaluate if RAG enhancement actually improved retrieval quality."""
        # Check if tool synthesis examples were injected for tool-related queries
        tool_keywords = ["tool", "create", "investigate", "analyze", "check"]
        is_tool_query = any(keyword in query.lower() for keyword in tool_keywords)

        if not is_tool_query:
            return False  # No improvement expected for non-tool queries

        # Check if enhanced docs contain tool synthesis examples
        enhanced_text = str(enhanced_docs).lower()
        return "tool synthesis" in enhanced_text or "tool creation" in enhanced_text

def main():
    """Test the real evolutionary integration system."""
    print("=== Testing Real Evolutionary Integration ===")

    integrator = RealEvolutionaryIntegrator()

    # Test memory integration with real components
    print("\n--- Testing Memory Integration with Real KLoROS ---")
    memory_code = '''
def memory_enhanced_chat_wrapper(kloros_instance, message: str) -> str:
    """Real memory-enhanced chat integration."""
    if hasattr(kloros_instance, "memory_enhanced") and kloros_instance.memory_enhanced:
        # Use real memory system
        context_result = kloros_instance.memory_enhanced._retrieve_context(message)
        if context_result and context_result.events:
            # Format real context
            context_text = f"[Context from {len(context_result.events)} previous interactions]"
            enhanced_message = f"{context_text}\\n\\n{message}"

            # Use real reasoning backend
            result = kloros_instance.reason_backend.reply(enhanced_message, kloros_instance=kloros_instance)
            return result.reply_text

    # Fallback to normal chat
    return kloros_instance.reason_backend.reply(message, kloros_instance=kloros_instance).reply_text
'''

    memory_test_cases = [
        {"input": "What did we discuss about tool synthesis?", "expect_context": True},
        {"input": "Create tool system_restart", "expect_context": False}
    ]

    memory_result = integrator.test_memory_integration_approach(memory_code, memory_test_cases)
    print(f"Memory Integration Result: Success={memory_result.success}, Score={memory_result.performance_score:.3f}")

    print("\n=== Real Integration Test Complete ===")

if __name__ == "__main__":
    main()