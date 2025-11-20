"""
D-REAM RAG Context Domain Evaluator
Optimizes conversational memory retrieval, context continuity, and semantic recall.
"""

import os
import sys
import json
import time
import random
from pathlib import Path
from typing import Dict, Any, Tuple, List
import logging

# Add dream path
sys.path.insert(0, '/home/kloros/src/dream')
from domains.domain_evaluator_base import DomainEvaluator

logger = logging.getLogger(__name__)


class RAGContextDomainEvaluator(DomainEvaluator):
    """Evaluates and optimizes RAG/memory context retrieval for conversation continuity."""

    def __init__(self):
        super().__init__("rag_context")

        # Test conversation scenarios for evaluation
        self.test_scenarios = [
            {
                "turns": [
                    "What is a critical system failure?",
                    "Can you give me an example of one?",  # Pronoun reference
                ],
                "expected_context": ["critical system failure"],
                "scenario_type": "pronoun_reference"
            },
            {
                "turns": [
                    "The audio system is having xruns",
                    "What could be causing that?",  # Demonstrative reference
                ],
                "expected_context": ["audio", "xruns"],
                "scenario_type": "demonstrative_reference"
            },
            {
                "turns": [
                    "I need to optimize GPU performance",
                    "Check the thermal status first",
                    "Did you find anything?",  # Multi-turn reference
                ],
                "expected_context": ["GPU", "thermal"],
                "scenario_type": "multi_turn"
            },
            {
                "turns": [
                    "The semantic reasoner failed to load",
                    "It says sentence transformers is missing",
                    "How do I fix it?",  # Pronoun chain
                ],
                "expected_context": ["semantic reasoner", "sentence transformers"],
                "scenario_type": "pronoun_chain"
            }
        ]

    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """
        Define RAG/memory context retrieval parameters.

        Returns:
            Dict mapping parameter names to (min, max, step) tuples
        """
        return {
            # Recent turns retrieval
            'recent_turns_count': (2, 10, 1),           # How many recent turns to always include
            'recent_turns_enabled': (0, 1, 1),          # Binary: always include recent context

            # Semantic similarity thresholds
            'semantic_threshold': (0.3, 0.8, 0.05),     # Distance cutoff for semantic matches
            'semantic_top_k': (2, 10, 1),               # Number of semantic results to retrieve

            # Time-based retrieval
            'time_window_hours': (1, 72, 1),            # How far back to search (1-72 hours)
            'recency_weight': (0.0, 1.0, 0.1),          # Boost score for recent memories

            # Retrieval strategy
            'use_hybrid_search': (0, 1, 1),             # Binary: use BM25+vector hybrid
            'bm25_weight': (0.0, 1.0, 0.1),             # BM25 vs vector weighting in hybrid
            'rrf_k': (20, 100, 10),                     # RRF fusion parameter

            # Context injection
            'max_context_tokens': (200, 1000, 50),      # Maximum context length to inject
            'dedup_threshold': (0.7, 1.0, 0.05),        # Similarity threshold for deduplication
        }

    def get_safety_constraints(self) -> Dict[str, Any]:
        """
        Define safety limits for RAG context parameters.

        Returns:
            Dict of constraint names to limit values
        """
        return {
            'recent_turns_min': {'min': 2},              # Always include at least 2 recent turns
            'semantic_threshold_max': {'max': 0.8},      # Don't reject too aggressively
            'time_window_min': {'min': 1},               # At least 1 hour lookback
            'max_context_reasonable': {'max': 1000},     # Don't overflow context window
        }

    def get_default_weights(self) -> Dict[str, float]:
        """
        Define fitness function weights for RAG context metrics.

        Returns:
            Dict of metric names to weight values
        """
        return {
            'context_recall': 0.35,           # Most important: retrieve relevant context
            'context_precision': 0.20,        # Avoid irrelevant context
            'follow_up_success': 0.25,        # Handle pronoun references
            'hallucination_rate': -0.15,      # Negative: penalize hallucinations
            'response_latency_ms': -0.05,     # Negative: penalize slow retrieval
        }

    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize metric to [0, 1] range."""
        normalizations = {
            'context_recall': lambda x: x,                           # Already 0-1
            'context_precision': lambda x: x,                        # Already 0-1
            'follow_up_success': lambda x: x,                        # Already 0-1
            'hallucination_rate': lambda x: 1.0 - min(x, 1.0),      # Invert: lower is better
            'response_latency_ms': lambda x: max(0.0, 1.0 - x / 1000.0),  # < 1000ms is good
            'context_tokens_used': lambda x: min(x / 500.0, 1.0),   # Up to 500 tokens
        }

        normalizer = normalizations.get(metric_name, lambda x: x)
        return max(0.0, min(1.0, normalizer(value)))

    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """
        Run RAG context probes (delegate to evaluate).

        Args:
            config: Configuration parameters

        Returns:
            Dict of measured metrics
        """
        return self.evaluate(config)

    def apply_config(self, config: Dict[str, Any]) -> bool:
        """
        Apply RAG context configuration by updating the reasoner's parameters.

        Args:
            config: Genome configuration to apply

        Returns:
            True if configuration applied successfully
        """
        try:
            # Convert numpy array to dict if needed
            import numpy as np
            if isinstance(config, np.ndarray):
                genome_spec = self.get_genome_spec()
                param_names = list(genome_spec.keys())
                config = {name: float(config[i]) if isinstance(config[i], (np.integer, np.floating)) else int(config[i])
                         for i, name in enumerate(param_names)}

            # Store config for retrieval during evaluation
            self.active_config = config

            # Update the RAG backend configuration file
            config_path = Path('/home/kloros/.kloros/rag_context_config.json')
            config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

            logger.info(f"Applied RAG context config: {config}")
            return True

        except Exception as e:
            logger.error(f"Failed to apply RAG context config: {e}")
            return False

    def reset_config(self) -> bool:
        """Reset to default RAG context configuration."""
        default_config = {
            'recent_turns_count': 6,
            'recent_turns_enabled': 1,
            'semantic_threshold': 0.6,
            'semantic_top_k': 5,
            'time_window_hours': 24,
            'recency_weight': 0.3,
            'use_hybrid_search': 1,
            'bm25_weight': 0.5,
            'rrf_k': 60,
            'max_context_tokens': 500,
            'dedup_threshold': 0.85,
        }
        return self.apply_config(default_config)

    def evaluate(self, config: Dict[str, Any]) -> Dict[str, float]:
        """
        Evaluate RAG context configuration across test scenarios.

        Args:
            config: Genome configuration to evaluate

        Returns:
            Dict of KPI metrics
        """
        # Convert numpy array to dict if needed for logging
        import numpy as np
        if isinstance(config, np.ndarray):
            genome_spec = self.get_genome_spec()
            param_names = list(genome_spec.keys())
            config_dict = {name: float(config[i]) if isinstance(config[i], (np.integer, np.floating)) else int(config[i])
                          for i, name in enumerate(param_names)}
            logger.info(f"Evaluating RAG context config: {config_dict}")
        else:
            logger.info(f"Evaluating RAG context config: {config}")

        # Apply configuration (will handle numpy conversion internally)
        if not self.apply_config(config):
            return self._get_failed_metrics()

        # Initialize metrics
        metrics = {
            'context_recall': 0.0,           # Did it retrieve relevant context?
            'context_precision': 0.0,        # Was retrieved context actually relevant?
            'follow_up_success': 0.0,        # Handled pronoun/demonstrative references?
            'hallucination_rate': 0.0,       # False memories injected?
            'response_latency_ms': 0.0,      # How long did retrieval take?
            'context_tokens_used': 0.0,      # How much context was injected?
        }

        try:
            # Test each scenario
            scenario_results = []

            for scenario in self.test_scenarios:
                result = self._test_scenario(scenario, config)
                scenario_results.append(result)

            # Aggregate metrics across scenarios
            if scenario_results:
                for key in metrics.keys():
                    values = [r[key] for r in scenario_results if key in r]
                    metrics[key] = sum(values) / len(values) if values else 0.0

            logger.info(f"RAG context evaluation complete: {metrics}")

        except Exception as e:
            logger.error(f"RAG context evaluation failed: {e}")
            return self._get_failed_metrics()

        return metrics

    def _test_scenario(self, scenario: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, float]:
        """Test a single conversation scenario."""
        turns = scenario['turns']
        expected_context = scenario['expected_context']

        # Simulate conversation flow
        simulated_history = []
        metrics = {
            'context_recall': 0.0,
            'context_precision': 0.0,
            'follow_up_success': 0.0,
            'hallucination_rate': 0.0,
            'response_latency_ms': 0.0,
            'context_tokens_used': 0.0,
        }

        try:
            # For each turn after the first
            for i, turn in enumerate(turns[1:], start=1):
                # Retrieve context using current config
                start_time = time.time()
                retrieved_context = self._retrieve_context(
                    query=turn,
                    history=simulated_history,
                    config=config
                )
                latency = (time.time() - start_time) * 1000  # ms

                # Check if expected context was retrieved
                recall_score = self._calculate_recall(retrieved_context, expected_context)
                precision_score = self._calculate_precision(retrieved_context, simulated_history)

                # Check for hallucinations (context not in actual history)
                hallucination_score = self._detect_hallucinations(retrieved_context, simulated_history)

                # Calculate tokens used
                tokens_used = sum(len(ctx.split()) for ctx in retrieved_context)

                metrics['context_recall'] += recall_score
                metrics['context_precision'] += precision_score
                metrics['hallucination_rate'] += hallucination_score
                metrics['response_latency_ms'] += latency
                metrics['context_tokens_used'] += tokens_used

                # Add this turn to history
                simulated_history.append(turn)

            # Average across turns
            num_turns = len(turns) - 1
            if num_turns > 0:
                for key in ['context_recall', 'context_precision', 'hallucination_rate',
                           'response_latency_ms', 'context_tokens_used']:
                    metrics[key] /= num_turns

            # Overall success: did it maintain context?
            metrics['follow_up_success'] = 1.0 if metrics['context_recall'] > 0.7 else 0.0

        except Exception as e:
            logger.warning(f"Scenario test failed: {e}")
            return self._get_failed_metrics()

        return metrics

    def _retrieve_context(self, query: str, history: List[str], config: Dict[str, Any]) -> List[str]:
        """Simulate context retrieval using config parameters."""
        retrieved = []

        # Always include recent turns if enabled
        recent_enabled = config.get('recent_turns_enabled', 1)
        recent_count = config.get('recent_turns_count', 6)

        if recent_enabled and history:
            retrieved.extend(history[-recent_count:])

        # Semantic matching (simplified - in real eval, use actual embeddings)
        semantic_threshold = config.get('semantic_threshold', 0.6)
        for hist_turn in history[:-recent_count if recent_enabled else None]:
            # Simple keyword overlap as proxy for semantic similarity
            query_words = set(query.lower().split())
            hist_words = set(hist_turn.lower().split())
            overlap = len(query_words & hist_words) / max(len(query_words), 1)

            # Convert overlap to "distance" (lower is better)
            distance = 1.0 - overlap

            if distance < semantic_threshold:
                retrieved.append(hist_turn)

        return retrieved

    def _calculate_recall(self, retrieved: List[str], expected: List[str]) -> float:
        """Calculate what fraction of expected context was retrieved."""
        if not expected:
            return 1.0

        retrieved_text = ' '.join(retrieved).lower()
        found_count = sum(1 for exp in expected if exp.lower() in retrieved_text)

        return found_count / len(expected)

    def _calculate_precision(self, retrieved: List[str], actual_history: List[str]) -> float:
        """Calculate what fraction of retrieved context was actually relevant."""
        if not retrieved:
            return 1.0  # No retrieval = no false positives

        relevant_count = sum(1 for ret in retrieved if ret in actual_history)
        return relevant_count / len(retrieved)

    def _detect_hallucinations(self, retrieved: List[str], actual_history: List[str]) -> float:
        """Detect if retrieved context contains hallucinated information."""
        if not retrieved:
            return 0.0

        hallucinated_count = sum(1 for ret in retrieved if ret not in actual_history)
        return hallucinated_count / len(retrieved)

    def _get_failed_metrics(self) -> Dict[str, float]:
        """Return metrics indicating evaluation failure."""
        return {
            'context_recall': 0.0,
            'context_precision': 0.0,
            'follow_up_success': 0.0,
            'hallucination_rate': 1.0,  # Maximum penalty
            'response_latency_ms': 9999.0,
            'context_tokens_used': 0.0,
        }


# Register the evaluator
if __name__ == "__main__":
    evaluator = RAGContextDomainEvaluator()
    print(f"RAG Context Domain Evaluator initialized")
    print(f"Genome parameters: {evaluator.get_genome_spec()}")
    print(f"Safety constraints: {evaluator.get_safety_constraints()}")
