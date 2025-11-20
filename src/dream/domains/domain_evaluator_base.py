#!/usr/bin/env python3
"""
Base Domain Evaluator Framework for D-REAM
Provides common interface for all subsystem evaluators.
"""

import os
import sys
import json
import time
import logging
import subprocess
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


class DomainEvaluator(ABC):
    """Base class for all domain evaluators."""

    def __init__(self, name: str):
        """
        Initialize domain evaluator.

        Args:
            name: Name of the domain (cpu, gpu, memory, etc.)
        """
        self.name = name
        self.telemetry_dir = Path(f"/home/kloros/src/dream/artifacts/domain_telemetry/{name}")
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)
        self.safety_violations = []
        self.last_evaluation = None
        self.current_regime = None  # NEW: Store current regime config

    @abstractmethod
    def get_genome_spec(self) -> Dict[str, Tuple[Any, Any, Any]]:
        """
        Get genome specification for this domain.

        Returns:
            Dict mapping parameter names to (min, max, step) tuples
        """
        pass

    @abstractmethod
    def get_safety_constraints(self) -> Dict[str, Any]:
        """
        Get safety constraints for this domain.

        Returns:
            Dict of constraint names to limit values
        """
        pass

    @abstractmethod
    def run_probes(self, config: Dict[str, Any]) -> Dict[str, float]:
        """
        Run performance probes with given configuration.

        Args:
            config: Configuration parameters for this run

        Returns:
            Dict of metric name to measured value
        """
        pass

    def genome_to_config(self, genome: List[float]) -> Dict[str, Any]:
        """
        Convert genome values to configuration parameters.

        Args:
            genome: List of normalized genome values

        Returns:
            Dict of parameter names to actual values
        """
        spec = self.get_genome_spec()
        config = {}

        for i, (param_name, (min_val, max_val, step)) in enumerate(spec.items()):
            if i >= len(genome):
                # Use midpoint as default
                normalized = 0.5
            else:
                # Normalize genome value to [0, 1] using tanh
                normalized = (np.tanh(genome[i]) + 1.0) / 2.0

            # Map to parameter range with stepping
            raw_value = min_val + normalized * (max_val - min_val)

            # Apply stepping
            if isinstance(step, (int, float)) and step > 0:
                # Round to nearest step
                if isinstance(min_val, int):
                    value = int(round(raw_value / step) * step)
                else:
                    value = round(raw_value / step) * step
            else:
                value = raw_value

            config[param_name] = value

        return config

    def check_safety(self, config: Dict[str, Any], metrics: Dict[str, float]) -> Tuple[bool, List[str]]:
        """
        Check if safety constraints are violated.

        Args:
            config: Current configuration
            metrics: Measured metrics

        Returns:
            Tuple of (is_safe, list_of_violations)
        """
        constraints = self.get_safety_constraints()
        violations = []

        for constraint_name, limit in constraints.items():
            if constraint_name in metrics:
                value = metrics[constraint_name]

                # Check different constraint types
                if isinstance(limit, dict):
                    if 'max' in limit and value > limit['max']:
                        violations.append(f"{constraint_name}={value} > {limit['max']}")
                    if 'min' in limit and value < limit['min']:
                        violations.append(f"{constraint_name}={value} < {limit['min']}")
                    if 'eq' in limit and value != limit['eq']:
                        violations.append(f"{constraint_name}={value} != {limit['eq']}")
                else:
                    # Simple max constraint
                    if value > limit:
                        violations.append(f"{constraint_name}={value} > {limit}")

        return len(violations) == 0, violations

    def calculate_fitness(self, metrics: Dict[str, float], weights: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate composite fitness score.

        Args:
            metrics: Measured metrics
            weights: Optional weight overrides

        Returns:
            Composite fitness score
        """
        if weights is None:
            weights = self.get_default_weights()

        fitness = 0.0

        for metric_name, weight in weights.items():
            if metric_name in metrics:
                # Normalize metric value based on expected range
                normalized = self.normalize_metric(metric_name, metrics[metric_name])
                fitness += weight * normalized

        return fitness

    @abstractmethod
    def get_default_weights(self) -> Dict[str, float]:
        """Get default fitness weights for this domain."""
        pass

    @abstractmethod
    def normalize_metric(self, metric_name: str, value: float) -> float:
        """Normalize a metric value to [0, 1] range."""
        pass

    def map_metrics_to_scoring(self, metrics: Dict[str, float]) -> Dict[str, float]:
        """
        Map domain-specific metric names to generic scoring names.

        Override this in domain evaluators to map:
        - Domain throughput metric -> 'perf'
        - Domain latency metric -> 'p95_ms'
        - Domain power metric -> 'watts'

        Args:
            metrics: Domain-specific metrics

        Returns:
            Metrics with additional generic keys for scoring
        """
        # Default: return metrics unchanged
        # Subclasses should override to add mappings
        return metrics

    def evaluate(self, genome_or_config, regime_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Main evaluation entry point for D-REAM.

        Args:
            genome_or_config: Either genome values (List[float]) or config dict (Dict[str, Any])
            regime_config: Optional regime configuration (workload, args, etc.)

        Returns:
            Dict with fitness, metrics, safety status
        """
        # Store regime config for run_probes to use
        self.current_regime = regime_config or {'workload': 'default', 'args': ''}

        # Convert genome to configuration (support both genome list and config dict)
        if isinstance(genome_or_config, dict):
            # Already a config dict - use directly
            config = genome_or_config
        else:
            # Genome list - convert to config
            config = self.genome_to_config(genome_or_config)

        # Log evaluation start
        self._log_telemetry('eval_start', {'config': config, 'regime': self.current_regime})

        # Run performance probes
        try:
            metrics = self.run_probes(config)
        except Exception as e:
            logger.error(f"Probe failed for {self.name}: {e}")
            return {
                'fitness': -float('inf'),
                'metrics': {},
                'config': config,
                'error': str(e),
                'safe': False
            }

        # Check safety constraints
        is_safe, violations = self.check_safety(config, metrics)

        if not is_safe:
            # Penalize unsafe configurations
            fitness = -float('inf')
            self.safety_violations.extend(violations)
        else:
            # Calculate fitness
            fitness = self.calculate_fitness(metrics)

        # Log evaluation result
        self._log_telemetry('eval_result', {
            'config': config,
            'regime': self.current_regime,
            'metrics': metrics,
            'fitness': fitness,
            'safe': is_safe,
            'violations': violations
        })

        self.last_evaluation = {
            'timestamp': datetime.now().isoformat(),
            'config': config,
            'regime': self.current_regime,
            'metrics': metrics,
            'fitness': fitness,
            'safe': is_safe,
            'violations': violations
        }

        return {
            'fitness': fitness,
            'metrics': metrics,
            'config': config,
            'safe': is_safe,
            'violations': violations
        }

    def _log_telemetry(self, event_type: str, data: Dict[str, Any]):
        """Log telemetry event."""
        event = {
            'timestamp': datetime.now().isoformat(),
            'domain': self.name,
            'event': event_type,
            'data': data
        }

        # Write to domain-specific telemetry file
        telemetry_file = self.telemetry_dir / f"{self.name}_telemetry.jsonl"
        try:
            with open(telemetry_file, 'a') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            logger.error(f"Failed to log telemetry: {e}")

    def run_command(self, cmd: List[str], timeout: int = 30) -> Tuple[int, str, str]:
        """
        Run a command and return results.

        Args:
            cmd: Command and arguments
            timeout: Timeout in seconds

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)

    def read_sysfs(self, path: str, default: Any = None) -> Any:
        """Read value from sysfs."""
        try:
            with open(path, 'r') as f:
                content = f.read().strip()
                # Try to convert to number if possible
                try:
                    if '.' in content:
                        return float(content)
                    else:
                        return int(content)
                except ValueError:
                    return content
        except Exception:
            return default

    def write_sysfs(self, path: str, value: Any) -> bool:
        """Write value to sysfs."""
        try:
            with open(path, 'w') as f:
                f.write(str(value))
            return True
        except PermissionError as e:
            logger.debug(f"Insufficient permissions to write {value} to {path} (expected in eval mode)")
            return False
        except Exception as e:
            logger.warning(f"Failed to write {value} to {path}: {e}")
            return False


class CompositeDomainEvaluator:
    """Combines multiple domain evaluators for full-system optimization."""

    def __init__(self, domains: List[DomainEvaluator]):
        """
        Initialize composite evaluator.

        Args:
            domains: List of domain evaluators to combine
        """
        self.domains = {d.name: d for d in domains}
        self.genome_map = self._build_genome_map()

    def _build_genome_map(self) -> Dict[str, Tuple[int, int]]:
        """Build mapping of domain to genome indices."""
        genome_map = {}
        current_idx = 0

        for name, domain in self.domains.items():
            spec = domain.get_genome_spec()
            genome_map[name] = (current_idx, current_idx + len(spec))
            current_idx += len(spec)

        return genome_map

    def evaluate(self, genome: List[float], domains: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Evaluate genome across specified domains.

        Args:
            genome: Full genome
            domains: Optional list of domains to evaluate (default: all)

        Returns:
            Combined evaluation results
        """
        if domains is None:
            domains = list(self.domains.keys())

        results = {}
        total_fitness = 0.0
        all_safe = True
        all_violations = []

        for domain_name in domains:
            if domain_name not in self.domains:
                continue

            # Extract genome slice for this domain
            start_idx, end_idx = self.genome_map[domain_name]
            domain_genome = genome[start_idx:end_idx] if start_idx < len(genome) else []

            # Evaluate domain
            domain_result = self.domains[domain_name].evaluate(domain_genome)

            results[domain_name] = domain_result

            # Aggregate results
            if domain_result['fitness'] != -float('inf'):
                total_fitness += domain_result['fitness']
            else:
                # Any unsafe domain makes total unsafe
                all_safe = False

            if not domain_result.get('safe', True):
                all_safe = False
                all_violations.extend(domain_result.get('violations', []))

        return {
            'fitness': total_fitness if all_safe else -float('inf'),
            'domain_results': results,
            'safe': all_safe,
            'violations': all_violations,
            'evaluated_domains': domains
        }
