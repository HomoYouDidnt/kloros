#!/usr/bin/env python3
"""
KLoROS Parameter Evaluator for D-REAM
Maps genome parameters to real KLoROS configurations and measures actual performance.
"""

import os
import sys
import json
import time
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class KLoROSEvaluator:
    """Evaluate KLoROS performance with different parameter configurations."""

    # Parameter ranges for genome mapping
    PARAM_RANGES = {
        # Audio processing parameters
        'input_gain': (1.0, 8.0),
        'vad_threshold': (0.01, 0.15),
        'vad_sensitivity': (0.2, 0.8),
        'vad_start_ms': (100, 500),
        'vad_min_speech_ms': (200, 600),
        'vad_max_silence_ms': (1500, 4000),

        # STT parameters
        'asr_correction_threshold': (0.5, 0.95),

        # Memory parameters
        'max_context_summaries': (3, 15),
        'max_context_events': (3, 12),
    }

    def __init__(self, base_env_path: str = "/home/kloros/.kloros_env"):
        """
        Initialize evaluator.

        Args:
            base_env_path: Path to base KLoROS environment configuration
        """
        self.base_env_path = base_env_path
        self.base_config = self._load_base_config()

    def _load_base_config(self) -> Dict[str, str]:
        """Load base configuration from .kloros_env."""
        config = {}
        if not os.path.exists(self.base_env_path):
            logger.warning(f"Base config not found: {self.base_env_path}")
            return config

        with open(self.base_env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()

        return config

    def genome_to_params(self, genome: List[float]) -> Dict[str, Any]:
        """
        Map genome values to KLoROS parameters.

        Args:
            genome: List of normalized values (typically from evolution)

        Returns:
            Dictionary mapping parameter names to values
        """
        if len(genome) < len(self.PARAM_RANGES):
            logger.warning(f"Genome too small ({len(genome)}), padding with zeros")
            genome = list(genome) + [0.0] * (len(self.PARAM_RANGES) - len(genome))

        params = {}
        for i, (param_name, (min_val, max_val)) in enumerate(self.PARAM_RANGES.items()):
            # Normalize genome value to [0, 1] range using tanh
            import numpy as np
            normalized = (np.tanh(genome[i]) + 1.0) / 2.0

            # Map to parameter range
            params[param_name] = min_val + normalized * (max_val - min_val)

        return params

    def params_to_env_vars(self, params: Dict[str, Any]) -> Dict[str, str]:
        """
        Convert parameter dictionary to environment variable format.

        Args:
            params: Parameter dictionary from genome_to_params

        Returns:
            Dictionary of environment variables
        """
        env_vars = {}

        # Audio processing
        if 'input_gain' in params:
            env_vars['KLR_INPUT_GAIN'] = f"{params['input_gain']:.2f}"
        if 'vad_threshold' in params:
            env_vars['KLR_VAD_THRESHOLD'] = f"{params['vad_threshold']:.3f}"
        if 'vad_sensitivity' in params:
            env_vars['KLR_VAD_SENSITIVITY'] = f"{params['vad_sensitivity']:.2f}"
        if 'vad_start_ms' in params:
            env_vars['KLR_VAD_START_MS'] = f"{int(params['vad_start_ms'])}"
        if 'vad_min_speech_ms' in params:
            env_vars['KLR_VAD_MIN_SPEECH_MS'] = f"{int(params['vad_min_speech_ms'])}"
        if 'vad_max_silence_ms' in params:
            env_vars['KLR_VAD_MAX_SILENCE_MS'] = f"{int(params['vad_max_silence_ms'])}"

        # STT parameters
        if 'asr_correction_threshold' in params:
            env_vars['ASR_CORRECTION_THRESHOLD'] = f"{params['asr_correction_threshold']:.2f}"

        # Memory parameters
        if 'max_context_summaries' in params:
            env_vars['KLR_MAX_CONTEXT_SUMMARIES'] = f"{int(params['max_context_summaries'])}"
        if 'max_context_events' in params:
            env_vars['KLR_MAX_CONTEXT_EVENTS'] = f"{int(params['max_context_events'])}"

        return env_vars

    def evaluate_params(self, params: Dict[str, Any]) -> Dict[str, float]:
        """
        Evaluate KLoROS performance with given parameters.

        Args:
            params: Parameter dictionary

        Returns:
            Metrics dictionary with performance measurements
        """
        # Convert params to env vars
        env_vars = self.params_to_env_vars(params)

        logger.info(f"Evaluating params: {json.dumps(params, indent=2)}")

        # Run actual tests
        metrics = {}

        # Test 1: Memory retrieval performance
        memory_perf = self._test_memory_performance(env_vars)
        metrics.update(memory_perf)

        # Test 2: Audio processing simulation
        audio_perf = self._test_audio_processing(params)
        metrics.update(audio_perf)

        # Test 3: Overall system health
        system_health = self._test_system_health(params)
        metrics.update(system_health)

        return metrics

    def _test_memory_performance(self, env_vars: Dict[str, str]) -> Dict[str, float]:
        """Test memory retrieval performance with configured parameters."""
        try:
            # Import memory components
            sys.path.insert(0, '/home/kloros/src')
            from kloros_memory.retriever import ContextRetriever
            from kloros_memory.storage import MemoryStore
            from kloros_memory.models import ContextRetrievalRequest

            # Create temporary env with overrides
            test_env = os.environ.copy()
            test_env.update(env_vars)

            # Update environment temporarily
            old_env = {}
            for key, value in env_vars.items():
                old_env[key] = os.environ.get(key)
                os.environ[key] = value

            try:
                # Initialize retriever
                storage = MemoryStore()
                retriever = ContextRetriever(storage)

                # Run test queries
                test_queries = [
                    "machine learning",
                    "audio processing",
                    "system performance",
                    "conversation history",
                    "optimization"
                ]

                start_time = time.time()
                total_events = 0
                total_summaries = 0

                for query in test_queries:
                    request = ContextRetrievalRequest(
                        query=query,
                        max_events=10,
                        max_summaries=5
                    )
                    result = retriever.retrieve_context(request)
                    total_events += len(result.events)
                    total_summaries += len(result.summaries)

                retrieval_time = time.time() - start_time
                avg_time = retrieval_time / len(test_queries)

                # Score: faster is better, more results is better
                speed_score = max(0, 1.0 - avg_time)  # Penalize slow retrieval
                total_results = total_events + total_summaries
                coverage_score = min(total_results / 50.0, 1.0)  # Reward good coverage

                return {
                    'memory_speed': speed_score,
                    'memory_coverage': coverage_score,
                    'memory_retrieval_time': avg_time
                }

            finally:
                # Restore environment
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        except Exception as e:
            logger.error(f"Memory performance test failed: {e}")
            return {
                'memory_speed': 0.0,
                'memory_coverage': 0.0,
                'memory_retrieval_time': 999.0
            }

    def _test_audio_processing(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Test audio processing parameters."""
        # Evaluate audio parameters for quality/responsiveness tradeoff

        # VAD sensitivity: higher = more responsive but more false triggers
        vad_sensitivity = params.get('vad_sensitivity', 0.4)
        vad_threshold = params.get('vad_threshold', 0.05)

        # Optimal range: 0.3-0.6 sensitivity, 0.03-0.08 threshold
        sensitivity_score = 1.0 - abs(vad_sensitivity - 0.45) / 0.45
        threshold_score = 1.0 - abs(vad_threshold - 0.055) / 0.055

        # Input gain: optimal around 4.0-5.0
        input_gain = params.get('input_gain', 4.0)
        gain_score = 1.0 - abs(input_gain - 4.5) / 4.5

        # VAD timing: balance responsiveness vs accuracy
        vad_start = params.get('vad_start_ms', 200)
        vad_min_speech = params.get('vad_min_speech_ms', 300)
        vad_max_silence = params.get('vad_max_silence_ms', 3000)

        # Prefer faster response but not too aggressive
        timing_score = (
            (1.0 - (vad_start - 100) / 400) * 0.3 +  # Prefer shorter start
            (1.0 - abs(vad_min_speech - 300) / 300) * 0.3 +  # Prefer ~300ms
            (1.0 - abs(vad_max_silence - 2500) / 2500) * 0.4  # Prefer ~2.5s
        )

        return {
            'audio_sensitivity_score': max(0, min(1, sensitivity_score)),
            'audio_threshold_score': max(0, min(1, threshold_score)),
            'audio_gain_score': max(0, min(1, gain_score)),
            'audio_timing_score': max(0, min(1, timing_score))
        }

    def _test_system_health(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Evaluate overall system health with these parameters."""

        # Memory context: balance between context and speed
        max_summaries = params.get('max_context_summaries', 10)
        max_events = params.get('max_context_events', 7)

        # Optimal: enough context but not overwhelming
        summary_score = 1.0 - abs(max_summaries - 8) / 8
        event_score = 1.0 - abs(max_events - 6) / 6

        # ASR correction: balance accuracy vs speed
        asr_threshold = params.get('asr_correction_threshold', 0.75)
        asr_score = 1.0 - abs(asr_threshold - 0.75) / 0.75

        return {
            'context_summary_score': max(0, min(1, summary_score)),
            'context_event_score': max(0, min(1, event_score)),
            'asr_threshold_score': max(0, min(1, asr_score))
        }

    def evaluate_individual(self, individual: Dict) -> Dict[str, float]:
        """
        Evaluate a D-REAM individual (main entry point).

        Args:
            individual: Dictionary with 'genome' key containing parameter vector

        Returns:
            Metrics dictionary for fitness scoring
        """
        genome = individual.get('genome', [])

        # Convert genome to parameters
        params = self.genome_to_params(genome)

        # Evaluate with those parameters
        metrics = self.evaluate_params(params)

        # Aggregate metrics into fitness-compatible format
        # perf: overall performance (higher is better)
        perf = (
            metrics.get('memory_speed', 0) * 0.2 +
            metrics.get('audio_gain_score', 0) * 0.2 +
            metrics.get('audio_timing_score', 0) * 0.2 +
            metrics.get('context_summary_score', 0) * 0.2 +
            metrics.get('asr_threshold_score', 0) * 0.2
        )

        # risk: lower is better (inverse of stability)
        risk = (
            (1.0 - metrics.get('audio_sensitivity_score', 0)) * 0.3 +
            (1.0 - metrics.get('audio_threshold_score', 0)) * 0.3 +
            (1.0 - metrics.get('context_event_score', 0)) * 0.4
        )

        # maxdd: maximum degradation (lower is better)
        maxdd = max(0, metrics.get('memory_retrieval_time', 1.0) - 0.5) * 0.2

        # turnover: parameter change magnitude (lower is better)
        turnover = 0.1  # Placeholder - could measure param deviation from baseline

        return {
            'perf': perf,
            'risk': risk,
            'maxdd': maxdd,
            'turnover': turnover,
            'raw_metrics': metrics,
            'params': params
        }


def test_evaluator():
    """Test the evaluator with sample genomes."""
    import numpy as np

    evaluator = KLoROSEvaluator()

    # Test with random genome
    genome = np.random.randn(len(evaluator.PARAM_RANGES))
    individual = {'genome': genome, 'id': 'test_ind'}

    metrics = evaluator.evaluate_individual(individual)

    print("\nEvaluation Results:")
    print(f"Performance: {metrics['perf']:.3f}")
    print(f"Risk: {metrics['risk']:.3f}")
    print(f"MaxDD: {metrics['maxdd']:.3f}")
    print(f"Turnover: {metrics['turnover']:.3f}")
    print(f"\nRaw metrics: {json.dumps(metrics['raw_metrics'], indent=2)}")
    print(f"\nParameters: {json.dumps(metrics['params'], indent=2)}")


if __name__ == '__main__':
    test_evaluator()
