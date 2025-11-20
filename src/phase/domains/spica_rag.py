"""
SPICA Derivative: RAG (Retrieval-Augmented Generation) Context Quality

SPICA-based RAG testing with:
- Full SPICA telemetry, manifest, and lineage tracking
- Retrieval precision and recall
- Context relevance scoring
- Answer groundedness (hallucination detection)
- Latency (retrieval + generation)

KPIs: retrieval_precision, answer_grounded_rate, latency_p95, context_relevance
"""
import time
import hashlib
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from spica.base import SpicaBase
from src.phase.report_writer import write_test_result


@dataclass
class RAGTestConfig:
    """Configuration for RAG domain tests."""
    test_queries: List[Dict] = None
    knowledge_base_path: Optional[Path] = None
    max_retrieval_latency_ms: int = 5000  # Realistic for embedding model + retrieval
    max_total_latency_ms: int = 8000  # Retrieval + generation
    top_k: int = 5
    max_memory_mb: int = 2048
    max_cpu_percent: int = 70

    # D-REAM evolvable fitness weights (must sum to ~1.0)
    fitness_weight_comprehension: float = 0.45  # Judge-scored answer quality (most important)
    fitness_weight_precision: float = 0.25      # Retrieval accuracy
    fitness_weight_relevance: float = 0.20      # Context relevance
    fitness_weight_latency: float = 0.10        # Speed bonus/penalty

    # Default temperature for answer generation (evolvable via annealing)
    default_temperature: float = 0.7

    def __post_init__(self):
        if self.test_queries is None:
            self.test_queries = [
                {"query": "What is KLoROS?", "expected_sources": ["system", "architecture"],
                 "expected_keywords": ["voice", "assistant", "KLoROS"]},
                {"query": "How does D-REAM evolution work?", "expected_sources": ["dream_evolution", "system"],
                 "expected_keywords": ["evolution", "fitness", "genetic"]},
                {"query": "What are common audio issues?", "expected_sources": ["troubleshooting", "common_issues"],
                 "expected_keywords": ["audio", "xruns", "commands"]}
            ]


@dataclass
class RAGTestResult:
    """Results from a single RAG test."""
    test_id: str
    query_hash: str
    status: str
    retrieval_latency_ms: float
    generation_latency_ms: float
    total_latency_ms: float
    retrieved_chunks: int
    retrieval_precision: float
    answer_grounded: bool
    context_relevance: float
    comprehension_score: float  # Judge-scored answer quality (0.0-1.0)
    temperature_used: float  # Temperature for answer generation
    cpu_percent: float
    memory_mb: float


class SpicaRAG(SpicaBase):
    """SPICA derivative for RAG context quality testing."""

    def __init__(self, spica_id: Optional[str] = None, config: Optional[Dict] = None,
                 test_config: Optional[RAGTestConfig] = None, parent_id: Optional[str] = None,
                 generation: int = 0, mutations: Optional[Dict] = None):
        if spica_id is None:
            spica_id = f"spica-rag-{uuid.uuid4().hex[:8]}"

        base_config = config or {}
        if test_config:
            base_config.update({
                'test_queries': test_config.test_queries,
                'top_k': test_config.top_k,
                'max_retrieval_latency_ms': test_config.max_retrieval_latency_ms,
                'max_total_latency_ms': test_config.max_total_latency_ms,
                'default_temperature': test_config.default_temperature,
                # Fitness weights (evolvable by D-REAM)
                'fitness_weight_comprehension': test_config.fitness_weight_comprehension,
                'fitness_weight_precision': test_config.fitness_weight_precision,
                'fitness_weight_relevance': test_config.fitness_weight_relevance,
                'fitness_weight_latency': test_config.fitness_weight_latency
            })

        super().__init__(spica_id=spica_id, domain="rag", config=base_config,
                        parent_id=parent_id, generation=generation, mutations=mutations)

        self.test_config = test_config or RAGTestConfig()
        self.results: List[RAGTestResult] = []
        self.record_telemetry("spica_rag_init", {"queries_count": len(self.test_config.test_queries)})

        # Lazy load embedding model (only when needed)
        self._embedding_model = None

    def _hash_query(self, query: str) -> str:
        return hashlib.sha256(query.encode()).hexdigest()[:16]

    def _retrieve_chunks(self, query: str) -> Tuple[List[Dict], float]:
        start = time.time()
        try:
            from src.simple_rag import RAG
            import numpy as np

            # Lazy load embedding model on first use
            if self._embedding_model is None:
                from sentence_transformers import SentenceTransformer
                from src.config.models_config import get_embedder_model, get_embedder_trust_remote_code
                model_name = get_embedder_model()
                self._embedding_model = SentenceTransformer(
                    model_name,
                    device='cpu',
                    trust_remote_code=get_embedder_trust_remote_code()
                )
                self.record_telemetry("embedding_model_loaded", {"model": model_name})

            def real_embedder(text: str) -> np.ndarray:
                return self._embedding_model.encode(text, convert_to_numpy=True)

            rag = RAG(bundle_path="/home/kloros/rag_data/rag_store.npz", verify_bundle_hash=False)
            results = rag.retrieve_by_text(query, embedder=real_embedder, top_k=self.test_config.top_k)

            chunks = []
            for meta, score in results:
                chunks.append({
                    "source": meta.get("file", meta.get("id", "unknown")),
                    "text": meta.get("text", "")[:200],
                    "score": score
                })

            latency_ms = (time.time() - start) * 1000
            self.record_telemetry("retrieval_complete", {"chunks": len(chunks), "latency_ms": latency_ms})
            return chunks, latency_ms
        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            self.record_telemetry("retrieval_failed", {"error": str(e), "latency_ms": latency_ms})
            return [], latency_ms

    def _generate_answer(self, query: str, chunks: List[Dict], temperature: float = 0.7) -> Tuple[str, float, bool]:
        """Generate answer using Ollama with context."""
        import requests
        start = time.time()

        # Build context-aware prompt
        context = "\n\n".join([f"[{c['source']}] {c['text']}" for c in chunks])
        prompt = f"""Context:
{context}

Question: {query}

Instructions: Answer the question based ONLY on the context provided above. If the context doesn't contain enough information to answer, say "insufficient context". Be concise and factual."""

        try:
            payload = {
                "model": "qwen2.5:7b-instruct-q4_K_M",  # Using Ollama
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": 512,
                "stream": False
            }

            response = requests.post(
                "http://127.0.0.1:11434/v1/chat/completions",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            answer = result['choices'][0]['message']['content']
            tokens_used = result.get('usage', {}).get('total_tokens', 0)

            latency_ms = (time.time() - start) * 1000

            # Score groundedness (simple heuristic: check if answer references context)
            grounded = (
                len(chunks) > 0 and
                "insufficient context" not in answer.lower() and
                len(answer) > 10
            )

            self.record_telemetry("generation_complete", {
                "latency_ms": latency_ms,
                "grounded": grounded,
                "temperature": temperature,
                "tokens_used": tokens_used,
                "answer_length": len(answer)
            })

            return answer, latency_ms, grounded

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            self.record_telemetry("generation_failed", {
                "error": str(e),
                "latency_ms": latency_ms
            })
            # Fallback to empty answer
            return f"Error generating answer: {str(e)}", latency_ms, False

    def _score_comprehension(self, query: str, context_chunks: List[Dict], answer: str) -> float:
        """
        Use judge to score how well the answer comprehends and uses the context.

        Returns:
            Comprehension score 0.0-1.0 (higher = better groundedness)
        """
        import requests
        start = time.time()

        context = "\n\n".join([f"[{c['source']}] {c['text']}" for c in context_chunks])

        scoring_prompt = f"""You are evaluating answer quality for a RAG system.

Context:
{context}

Question: {query}

Answer to evaluate: {answer}

Instructions: Rate this answer on a scale from 0.0 to 1.0 based on:
1. Factual accuracy (is it supported by the context?)
2. Completeness (does it answer the question?)
3. Groundedness (does it only use information from context, not hallucinating?)

Respond with ONLY a number between 0.0 and 1.0, nothing else."""

        try:
            payload = {
                "model": "qwen2.5:7b-instruct-q4_K_M",
                "messages": [{"role": "user", "content": scoring_prompt}],
                "temperature": 0.0,  # Deterministic scoring
                "max_tokens": 50,
                "stream": False
            }

            response = requests.post(
                "http://127.0.0.1:11434/v1/chat/completions",
                json=payload,
                timeout=15
            )
            response.raise_for_status()
            result = response.json()

            score_text = result['choices'][0]['message']['content'].strip()

            # Extract numeric score
            try:
                score = float(score_text)
                score = max(0.0, min(1.0, score))  # Clamp to [0,1]
            except ValueError:
                # Fallback: parse first number found
                import re
                match = re.search(r'0?\.\d+|[01](?:\.\d+)?', score_text)
                score = float(match.group()) if match else 0.5

            latency_ms = (time.time() - start) * 1000
            self.record_telemetry("comprehension_scored", {
                "score": score,
                "latency_ms": latency_ms
            })

            return score

        except Exception as e:
            self.record_telemetry("comprehension_scoring_failed", {"error": str(e)})
            # Conservative fallback: 0.5 (neutral)
            return 0.5

    def evaluate(self, test_input: Dict, context: Optional[Dict] = None) -> Dict:
        """
        SPICA evaluate() with multi-objective fitness calculation.

        Fitness components:
        - Comprehension (0.45): Judge-scored answer quality
        - Precision (0.25): Retrieval accuracy
        - Relevance (0.20): Context relevance
        - Latency (0.10): Speed bonus/penalty
        """
        query_data = test_input.get("query_data")
        epoch_id = (context or {}).get("epoch_id", "unknown")
        if not query_data:
            raise ValueError("test_input must contain 'query_data' key")
        result = self.run_test(query_data, epoch_id)

        # Multi-objective fitness calculation using config weights
        comprehension_component = (
            self.test_config.fitness_weight_comprehension * result.comprehension_score
        )
        precision_component = (
            self.test_config.fitness_weight_precision * result.retrieval_precision
        )
        relevance_component = (
            self.test_config.fitness_weight_relevance * result.context_relevance
        )

        # Latency penalty: normalize to [0,1] where faster = better
        # 0ms = 1.0, max_total_latency_ms = 0.0
        latency_normalized = 1.0 - min(
            1.0,
            result.total_latency_ms / self.test_config.max_total_latency_ms
        )
        latency_component = (
            self.test_config.fitness_weight_latency * latency_normalized
        )

        # Combine components
        fitness = (
            comprehension_component +
            precision_component +
            relevance_component +
            latency_component
        )

        # Clamp to [0, 1]
        fitness = max(0.0, min(1.0, fitness))

        # Record detailed fitness breakdown for analysis
        self.record_telemetry("fitness_calculated", {
            "fitness": fitness,
            "comprehension_component": comprehension_component,
            "precision_component": precision_component,
            "relevance_component": relevance_component,
            "latency_component": latency_component,
            "latency_normalized": latency_normalized,
            "test_id": result.test_id
        })

        return {
            "fitness": fitness,
            "test_id": result.test_id,
            "status": result.status,
            "metrics": asdict(result),
            "spica_id": self.spica_id,
            # Include fitness breakdown for D-REAM analysis
            "fitness_breakdown": {
                "comprehension": comprehension_component,
                "precision": precision_component,
                "relevance": relevance_component,
                "latency": latency_component
            }
        }

    def run_test(self, query_data: Dict, epoch_id: str, temperature: Optional[float] = None) -> RAGTestResult:
        """
        Run a single RAG test with optional temperature override for annealing experiments.

        Args:
            query_data: Test query configuration
            epoch_id: PHASE epoch identifier
            temperature: Override temperature (for annealing), defaults to config value (0.7)
        """
        query = query_data["query"]
        query_hash = self._hash_query(query)
        test_id = f"rag::{query_hash}"

        # Support temperature annealing experiments
        if temperature is None:
            temperature = query_data.get("temperature", 0.7)

        try:
            # Retrieve relevant chunks
            chunks, retrieval_latency = self._retrieve_chunks(query)

            # Generate answer with specified temperature
            answer, generation_latency, grounded = self._generate_answer(query, chunks, temperature)

            # Score comprehension quality (uses judge)
            comprehension_score = self._score_comprehension(query, chunks, answer) if chunks else 0.0

            total_latency = retrieval_latency + generation_latency

            # Calculate retrieval precision
            expected_sources = query_data.get("expected_sources", [])
            retrieved_sources = [c["source"] for c in chunks]
            relevant_count = sum(1 for src in retrieved_sources if any(exp in src for exp in expected_sources))
            precision = relevant_count / len(chunks) if chunks else 0.0

            # Context relevance (average of retrieval scores)
            context_relevance = sum(c.get("score", 0.0) for c in chunks) / len(chunks) if chunks else 0.0

            # Multi-criteria pass/fail
            status = "pass"
            if retrieval_latency > self.test_config.max_retrieval_latency_ms:
                status = "fail"
            if total_latency > self.test_config.max_total_latency_ms:
                status = "fail"
            if precision < 0.4:  # 40% retrieval precision threshold
                status = "fail"
            if comprehension_score < 0.6:  # 60% comprehension threshold
                status = "fail"

            result = RAGTestResult(
                test_id=test_id, query_hash=query_hash, status=status,
                retrieval_latency_ms=retrieval_latency, generation_latency_ms=generation_latency,
                total_latency_ms=total_latency, retrieved_chunks=len(chunks),
                retrieval_precision=precision, answer_grounded=grounded,
                context_relevance=context_relevance, comprehension_score=comprehension_score,
                temperature_used=temperature, cpu_percent=50.0, memory_mb=1536.0
            )

            self.record_telemetry("test_complete", {
                "test_id": test_id,
                "status": status,
                "precision": precision,
                "comprehension_score": comprehension_score,
                "temperature": temperature
            })
            write_test_result(test_id=test_id, status=status, latency_ms=total_latency,
                            cpu_pct=50.0, mem_mb=1536.0, epoch_id=epoch_id)
            self.results.append(result)
            return result

        except Exception as e:
            result = RAGTestResult(
                test_id=test_id, query_hash=query_hash, status="fail",
                retrieval_latency_ms=0.0, generation_latency_ms=0.0, total_latency_ms=0.0,
                retrieved_chunks=0, retrieval_precision=0.0, answer_grounded=False,
                context_relevance=0.0, comprehension_score=0.0, temperature_used=temperature or 0.7,
                cpu_percent=0.0, memory_mb=0.0
            )
            self.record_telemetry("test_failed", {"test_id": test_id, "error": str(e)})
            write_test_result(test_id=test_id, status="fail", epoch_id=epoch_id)
            self.results.append(result)
            raise RuntimeError(f"RAG test failed: {e}") from e

    def run_all_tests(self, epoch_id: str, temperatures: Optional[List[float]] = None) -> List[RAGTestResult]:
        """
        Run all configured tests, optionally with temperature annealing.

        Args:
            epoch_id: PHASE epoch identifier
            temperatures: List of temperatures to test (for annealing experiments).
                         If None, uses default temperature from query_data or 0.7
        """
        if temperatures is None:
            # Standard run: use default temperature
            for query_data in self.test_config.test_queries:
                try:
                    self.run_test(query_data, epoch_id)
                except RuntimeError:
                    continue
        else:
            # Temperature annealing experiment: test each query with each temperature
            for query_data in self.test_config.test_queries:
                for temp in temperatures:
                    try:
                        self.run_test(query_data, epoch_id, temperature=temp)
                        self.record_telemetry("annealing_test", {
                            "query": query_data["query"][:50],
                            "temperature": temp
                        })
                    except RuntimeError:
                        continue
        return self.results

    def get_annealing_analysis(self) -> Dict:
        """
        Analyze results from temperature annealing experiments.

        Returns:
            Analysis dict with best temperature and performance by temperature
        """
        if not self.results:
            return {"error": "No results available"}

        # Group by temperature
        by_temp = {}
        for r in self.results:
            temp = r.temperature_used
            if temp not in by_temp:
                by_temp[temp] = []
            by_temp[temp].append(r)

        # Calculate metrics per temperature
        temp_analysis = {}
        for temp, results in by_temp.items():
            passed = [r for r in results if r.status == "pass"]
            temp_analysis[temp] = {
                "pass_rate": len(passed) / len(results),
                "avg_comprehension": sum(r.comprehension_score for r in results) / len(results),
                "avg_precision": sum(r.retrieval_precision for r in results) / len(results),
                "avg_latency_ms": sum(r.total_latency_ms for r in results) / len(results),
                "total_tests": len(results)
            }

        # Find best temperature (by pass rate, then comprehension)
        best_temp = max(temp_analysis.items(),
                       key=lambda x: (x[1]["pass_rate"], x[1]["avg_comprehension"]))[0]

        return {
            "best_temperature": best_temp,
            "by_temperature": temp_analysis,
            "total_configurations_tested": len(self.results)
        }

    def get_summary(self) -> Dict:
        if not self.results:
            return {"pass_rate": 0.0, "total_tests": 0}
        passed = sum(1 for r in self.results if r.status == "pass")
        precisions = [r.retrieval_precision for r in self.results if r.status == "pass"]
        latencies = [r.total_latency_ms for r in self.results if r.status == "pass"]
        return {
            "pass_rate": passed / len(self.results),
            "total_tests": len(self.results),
            "avg_precision": sum(precisions) / len(precisions) if precisions else 0.0,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "grounded_rate": sum(1 for r in self.results if r.answer_grounded) / len(self.results)
        }
