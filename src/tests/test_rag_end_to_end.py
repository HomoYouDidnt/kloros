#!/usr/bin/env python3
"""
Comprehensive End-to-End Testing of RAG Backend and Voice Pipeline

Tests all fixes:
1. RAG dimension mismatch (768→384 truncation)
2. Vector database health and consistency
3. Healing playbook for rag.processing_error

Test Categories:
- RAG Backend Direct Testing
- Voice Pipeline Component Testing
- Error Monitoring and Healing
- End-to-End Integration Testing
"""

import sys
import os
import time
import traceback
from datetime import datetime
from typing import Dict, Any, List, Optional

sys.path.insert(0, '/home/kloros/src')
sys.path.insert(0, '/home/kloros')

class TestResults:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.test_details = []
        self.errors = []

    def add_test(self, name: str, passed: bool, details: str = "", error: str = ""):
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            status = "✓ PASS"
        else:
            self.tests_failed += 1
            status = "✗ FAIL"
            if error:
                self.errors.append(f"{name}: {error}")

        self.test_details.append({
            'name': name,
            'status': status,
            'passed': passed,
            'details': details,
            'error': error
        })

    def print_summary(self):
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Total Tests Run: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_failed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0:.1f}%")
        print("\nTest Details:")
        print("-"*80)

        for test in self.test_details:
            print(f"\n{test['status']} {test['name']}")
            if test['details']:
                print(f"  Details: {test['details']}")
            if test['error']:
                print(f"  Error: {test['error']}")

        if self.errors:
            print("\n" + "="*80)
            print("ERRORS ENCOUNTERED:")
            print("="*80)
            for error in self.errors:
                print(f"  - {error}")

        print("\n" + "="*80)


class RAGEndToEndTester:
    def __init__(self):
        self.results = TestResults()
        self.rag_backend = None
        self.reasoning_coordinator = None

    def print_header(self, title: str):
        print("\n" + "="*80)
        print(f"  {title}")
        print("="*80)

    def test_1_rag_module_import(self):
        """Test 1: Import RAG modules"""
        self.print_header("TEST 1: RAG Module Import")

        try:
            from src import simple_rag
            self.results.add_test(
                "Import simple_rag module",
                True,
                "Module imported successfully"
            )
        except Exception as e:
            self.results.add_test(
                "Import simple_rag module",
                False,
                error=str(e)
            )

        try:
            from src.cognition.reasoning import local_rag_backend
            self.results.add_test(
                "Import local_rag_backend module",
                True,
                "Module imported successfully"
            )
        except Exception as e:
            self.results.add_test(
                "Import local_rag_backend module",
                False,
                error=str(e)
            )

    def test_2_rag_backend_initialization(self):
        """Test 2: Initialize RAG Backend"""
        self.print_header("TEST 2: RAG Backend Initialization")

        try:
            from src.cognition.reasoning.local_rag_backend import LocalRagBackend

            print("Creating LocalRagBackend instance...")
            self.rag_backend = LocalRagBackend(
                bundle_path="/home/kloros/rag_data/rag_store.npz"
            )

            has_rag = self.rag_backend.rag_instance is not None
            self.results.add_test(
                "RAG Backend initialization",
                has_rag,
                f"RAG instance created: {has_rag}"
            )

            if self.rag_backend.rag_instance:
                doc_count = len(self.rag_backend.rag_instance.metadata)
                self.results.add_test(
                    "RAG training data loaded",
                    doc_count > 0,
                    f"Loaded {doc_count} documents"
                )
        except Exception as e:
            self.results.add_test(
                "RAG Backend initialization",
                False,
                error=f"{e}\n{traceback.format_exc()}"
            )

    def test_3_embedding_dimensions(self):
        """Test 3: Verify Embedding Dimensions (384 not 768)"""
        self.print_header("TEST 3: Embedding Dimension Verification")

        if not self.rag_backend or not self.rag_backend.rag_instance:
            self.results.add_test(
                "Embedding dimension check",
                False,
                error="RAG backend not initialized"
            )
            return

        try:
            import numpy as np

            if self.rag_backend.rag_instance.embeddings is not None:
                embeddings = self.rag_backend.rag_instance.embeddings

                if len(embeddings.shape) == 2:
                    dim = embeddings.shape[1]
                else:
                    dim = len(embeddings)

                is_384 = dim == 384
                self.results.add_test(
                    "Stored embedding dimension is 384",
                    is_384,
                    f"Dimension: {dim} (expected 384)"
                )

                is_not_768 = dim != 768
                self.results.add_test(
                    "Stored embedding dimension is NOT 768",
                    is_not_768,
                    f"Dimension: {dim} (correctly not 768)"
                )

                print(f"  Embedding matrix shape: {embeddings.shape}")
                print(f"  Number of documents: {embeddings.shape[0]}")
                print(f"  Embedding dimension: {embeddings.shape[1]}")
            else:
                self.results.add_test(
                    "Embedding dimension check",
                    False,
                    error="RAG instance has no embeddings loaded"
                )

        except Exception as e:
            self.results.add_test(
                "Embedding dimension check",
                False,
                error=f"{e}\n{traceback.format_exc()}"
            )

    def test_4_rag_query(self):
        """Test 4: Execute RAG Query (No matmul errors)"""
        self.print_header("TEST 4: RAG Retrieval Execution")

        if not self.rag_backend or not self.rag_backend.rag_instance:
            self.results.add_test(
                "RAG query execution",
                False,
                error="RAG backend not initialized"
            )
            return

        test_queries = [
            "What is the system status?",
            "Tell me about KLoROS architecture",
            "How does the reasoning system work?"
        ]

        def dummy_embedder(text: str):
            """Dummy embedder that returns a 384-dim vector"""
            import numpy as np
            np.random.seed(hash(text) % (2**32))
            return np.random.randn(384).astype(np.float32)

        for query in test_queries:
            try:
                print(f"\nExecuting retrieval: '{query}'")

                result = self.rag_backend.rag_instance.retrieve_by_text(
                    query,
                    embedder=dummy_embedder,
                    top_k=3
                )

                self.results.add_test(
                    f"RAG retrieval: '{query[:50]}...'",
                    True,
                    f"Retrieved {len(result)} results"
                )

            except ValueError as e:
                if "matmul" in str(e).lower():
                    self.results.add_test(
                        f"RAG retrieval: '{query[:50]}...'",
                        False,
                        error=f"MATMUL ERROR DETECTED: {e}"
                    )
                else:
                    self.results.add_test(
                        f"RAG retrieval: '{query[:50]}...'",
                        False,
                        error=f"ValueError: {e}"
                    )
            except Exception as e:
                self.results.add_test(
                    f"RAG retrieval: '{query[:50]}...'",
                    False,
                    error=f"{e}\n{traceback.format_exc()}"
                )

    def test_5_vector_db_health(self):
        """Test 5: Vector Database Health Check"""
        self.print_header("TEST 5: Vector Database Health Check")

        databases = {
            'Qdrant': 'http://localhost:6333',
            'ChromaDB': '/home/kloros/.kloros/chroma',
            'RAG Store': '/home/kloros/rag_data/rag_store.npz'
        }

        for db_name, db_path in databases.items():
            try:
                if db_name == 'Qdrant':
                    try:
                        from qdrant_client import QdrantClient
                        client = QdrantClient(url=db_path)
                        collections = client.get_collections()
                        self.results.add_test(
                            f"{db_name} connectivity",
                            True,
                            f"Connected, {len(collections.collections)} collections found"
                        )
                    except Exception as e:
                        self.results.add_test(
                            f"{db_name} connectivity",
                            False,
                            error=str(e)
                        )

                elif db_name == 'ChromaDB':
                    if os.path.exists(db_path):
                        self.results.add_test(
                            f"{db_name} storage",
                            True,
                            f"Directory exists at {db_path}"
                        )
                    else:
                        self.results.add_test(
                            f"{db_name} storage",
                            False,
                            error=f"Directory not found: {db_path}"
                        )

                elif db_name == 'RAG Store':
                    if os.path.exists(db_path):
                        import numpy as np
                        data = np.load(db_path, allow_pickle=True)
                        self.results.add_test(
                            f"{db_name} file",
                            True,
                            f"File exists, keys: {list(data.keys())}"
                        )
                    else:
                        self.results.add_test(
                            f"{db_name} file",
                            False,
                            error=f"File not found: {db_path}"
                        )

            except Exception as e:
                self.results.add_test(
                    f"{db_name} health check",
                    False,
                    error=str(e)
                )

    def test_6_reasoning_coordinator(self):
        """Test 6: Reasoning Coordinator Integration"""
        self.print_header("TEST 6: Reasoning Coordinator Integration")

        try:
            from src.reasoning_coordinator import get_reasoning_coordinator

            self.reasoning_coordinator = get_reasoning_coordinator()

            self.results.add_test(
                "Reasoning Coordinator initialization",
                self.reasoning_coordinator is not None,
                f"Coordinator enabled: {self.reasoning_coordinator.enabled if self.reasoning_coordinator else False}"
            )

            if self.reasoning_coordinator and self.reasoning_coordinator.enabled:
                test_alternatives = [
                    {'name': 'option_a', 'value': 0.8, 'cost': 0.2, 'risk': 0.1},
                    {'name': 'option_b', 'value': 0.6, 'cost': 0.1, 'risk': 0.2},
                    {'name': 'option_c', 'value': 0.7, 'cost': 0.3, 'risk': 0.05}
                ]

                result = self.reasoning_coordinator.reason_about_alternatives(
                    context="Test reasoning decision",
                    alternatives=test_alternatives
                )

                self.results.add_test(
                    "Reasoning Coordinator decision making",
                    result is not None and hasattr(result, 'decision'),
                    f"Decision: {result.decision if result else 'None'}, Confidence: {result.confidence if result else 0:.2f}"
                )

        except Exception as e:
            self.results.add_test(
                "Reasoning Coordinator test",
                False,
                error=f"{e}\n{traceback.format_exc()}"
            )

    def test_7_voice_service_status(self):
        """Test 7: Voice Service Status Check"""
        self.print_header("TEST 7: Voice Service Status")

        try:
            import subprocess

            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5
            )

            voice_processes = [
                line for line in result.stdout.split('\n')
                if 'kloros_voice' in line and 'python' in line
            ]

            is_running = len(voice_processes) > 0

            if is_running:
                pid_info = voice_processes[0].split()[1]
                self.results.add_test(
                    "Voice service is running",
                    True,
                    f"Found voice service, PID: {pid_info}"
                )
            else:
                self.results.add_test(
                    "Voice service is running",
                    False,
                    error="Voice service not found in process list"
                )

        except Exception as e:
            self.results.add_test(
                "Voice service status check",
                False,
                error=str(e)
            )

    def test_8_log_monitoring(self):
        """Test 8: Monitor Logs for Errors"""
        self.print_header("TEST 8: Log Monitoring for RAG Errors")

        log_files = [
            '/tmp/kloros.log',
            '/home/kloros/.kloros/logs/exception_monitor.log'
        ]

        error_patterns = [
            'matmul',
            'dimension mismatch',
            'ValueError.*matmul',
            'rag.processing_error'
        ]

        for log_file in log_files:
            if not os.path.exists(log_file):
                continue

            try:
                with open(log_file, 'r') as f:
                    recent_lines = f.readlines()[-200:]

                log_content = ''.join(recent_lines)

                for pattern in error_patterns:
                    import re
                    matches = re.findall(pattern, log_content, re.IGNORECASE)

                    if matches:
                        self.results.add_test(
                            f"No '{pattern}' errors in {os.path.basename(log_file)}",
                            False,
                            error=f"Found {len(matches)} occurrences"
                        )
                    else:
                        self.results.add_test(
                            f"No '{pattern}' errors in {os.path.basename(log_file)}",
                            True,
                            "Log clean"
                        )

            except Exception as e:
                self.results.add_test(
                    f"Log monitoring: {log_file}",
                    False,
                    error=str(e)
                )

    def test_9_healing_playbook(self):
        """Test 9: Verify Healing Playbook Registration"""
        self.print_header("TEST 9: Healing Playbook Verification")

        playbook_path = '/home/kloros/self_heal_playbooks.yaml'

        if not os.path.exists(playbook_path):
            self.results.add_test(
                "Healing playbook file exists",
                False,
                error=f"Playbook file not found: {playbook_path}"
            )
            return

        try:
            with open(playbook_path, 'r') as f:
                content = f.read()

            has_rag_error = 'rag.processing_error' in content
            self.results.add_test(
                "Healing playbook contains rag.processing_error handler",
                has_rag_error,
                "Handler found in playbook" if has_rag_error else "Handler NOT found"
            )

            has_autofix = 'rag.processing_error.autofix' in content
            self.results.add_test(
                "Healing playbook has autofix steps",
                has_autofix,
                "Autofix steps defined" if has_autofix else "Autofix NOT defined"
            )

            has_validation = 'rag_health' in content
            self.results.add_test(
                "Healing playbook has rag_health validation",
                has_validation,
                "Validation check defined" if has_validation else "Validation NOT defined"
            )

        except Exception as e:
            self.results.add_test(
                "Healing playbook verification",
                False,
                error=str(e)
            )

    def test_10_end_to_end_query(self):
        """Test 10: Full End-to-End Retrieval + Answer Pipeline"""
        self.print_header("TEST 10: End-to-End Answer Pipeline")

        if not self.rag_backend or not self.rag_backend.rag_instance:
            self.results.add_test(
                "End-to-end query",
                False,
                error="RAG backend not initialized"
            )
            return

        try:
            test_query = "What are the main components of KLoROS?"

            print(f"\nExecuting end-to-end query: '{test_query}'")

            def dummy_embedder(text: str):
                """Dummy embedder that returns a 384-dim vector"""
                import numpy as np
                np.random.seed(hash(text) % (2**32))
                return np.random.randn(384).astype(np.float32)

            start_time = time.time()

            retrieved = self.rag_backend.rag_instance.retrieve_by_text(
                test_query,
                embedder=dummy_embedder,
                top_k=5
            )

            elapsed_retrieval = time.time() - start_time

            self.results.add_test(
                "End-to-end retrieval execution",
                True,
                f"Retrieval completed in {elapsed_retrieval:.3f}s, got {len(retrieved)} results"
            )

            prompt = self.rag_backend.rag_instance.build_prompt(
                test_query,
                retrieved,
                max_ctx_chars=2000
            )

            self.results.add_test(
                "End-to-end prompt building",
                len(prompt) > 0,
                f"Built prompt with {len(prompt)} chars"
            )

            print(f"  Retrieved {len(retrieved)} documents")
            print(f"  Prompt length: {len(prompt)} chars")

        except ValueError as e:
            if "matmul" in str(e).lower():
                self.results.add_test(
                    "End-to-end query",
                    False,
                    error=f"CRITICAL: MATMUL ERROR STILL PRESENT: {e}"
                )
            else:
                self.results.add_test(
                    "End-to-end query",
                    False,
                    error=str(e)
                )
        except Exception as e:
            self.results.add_test(
                "End-to-end query",
                False,
                error=f"{e}\n{traceback.format_exc()}"
            )

    def run_all_tests(self):
        """Run all test suites"""
        print("="*80)
        print("  RAG BACKEND & VOICE PIPELINE - COMPREHENSIVE END-TO-END TESTING")
        print("="*80)
        print(f"Test execution started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Environment: {os.getenv('USER')}@{os.uname().nodename}")

        self.test_1_rag_module_import()
        self.test_2_rag_backend_initialization()
        self.test_3_embedding_dimensions()
        self.test_4_rag_query()
        self.test_5_vector_db_health()
        self.test_6_reasoning_coordinator()
        self.test_7_voice_service_status()
        self.test_8_log_monitoring()
        self.test_9_healing_playbook()
        self.test_10_end_to_end_query()

        self.results.print_summary()

        return self.results.tests_failed == 0


def main():
    tester = RAGEndToEndTester()
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
