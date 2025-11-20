from typing import Dict
from .weights import FitnessWeights
from .composite import CompositeFitness
from .domain import DomainFitness


def create_fitness_from_config(config: Dict) -> CompositeFitness:
    """
    Factory function to create fitness from config.

    Args:
        config: Configuration dictionary with 'weights' and optional 'hard_caps'

    Returns:
        Configured CompositeFitness instance
    """
    # Extract weights dict
    weights_config = config.get("weights", {})

    # Create FitnessWeights if it's a dict, otherwise use as-is
    if isinstance(weights_config, dict):
        weights = FitnessWeights(**{k: v for k, v in weights_config.items()
                                     if k in ['perf', 'stability', 'maxdd', 'turnover', 'corr', 'risk']},
                                 weights={k: v for k, v in weights_config.items()
                                         if k not in ['perf', 'stability', 'maxdd', 'turnover', 'corr', 'risk']})
    else:
        weights = weights_config

    hard_caps = config.get("hard_caps", {})
    return CompositeFitness(weights, hard_caps)


def evaluate_fitness(episode_result: Dict, genome: 'Genome') -> 'FitnessMetrics':
    """
    Evaluate fitness from episode results for D-REAM evolution.
    Re-exported from src.dream.fitness module for backward compatibility.

    Args:
        episode_result: Episode execution results
        genome: Genome being evaluated

    Returns:
        FitnessMetrics with computed fitness score
    """
    from src.dream import fitness as fitness_module
    return fitness_module.evaluate_fitness(episode_result, genome)


__all__ = ["FitnessWeights", "CompositeFitness", "DomainFitness", "create_fitness_from_config", "evaluate_fitness"]
