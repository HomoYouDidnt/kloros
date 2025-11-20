"""Mutation operators for D-REAM evolution."""
import random
import copy
from typing import Dict, Any
from .dream_types import Genome


def mutate_budgets(genome: Genome, mutation_rate: float = 0.3) -> Genome:
    """Mutate budget parameters.

    Args:
        genome: Genome to mutate
        mutation_rate: Probability of mutation

    Returns:
        Mutated genome
    """
    mutated = copy.deepcopy(genome)

    if random.random() < mutation_rate:
        # Adjust latency budget
        factor = random.uniform(0.8, 1.2)
        mutated.budgets["latency_ms"] = int(mutated.budgets["latency_ms"] * factor)
        mutated.budgets["latency_ms"] = max(2000, min(10000, mutated.budgets["latency_ms"]))

    if random.random() < mutation_rate:
        # Adjust tool calls budget
        delta = random.choice([-1, 1])
        mutated.budgets["tool_calls"] += delta
        mutated.budgets["tool_calls"] = max(2, min(8, mutated.budgets["tool_calls"]))

    if random.random() < mutation_rate:
        # Adjust tokens budget
        factor = random.uniform(0.85, 1.15)
        mutated.budgets["tokens"] = int(mutated.budgets["tokens"] * factor)
        mutated.budgets["tokens"] = max(1000, min(6000, mutated.budgets["tokens"]))

    return mutated


def mutate_planner_config(genome: Genome, mutation_rate: float = 0.2) -> Genome:
    """Mutate planner configuration.

    Args:
        genome: Genome to mutate
        mutation_rate: Probability of mutation

    Returns:
        Mutated genome
    """
    mutated = copy.deepcopy(genome)

    # RA³ fallback threshold
    if random.random() < mutation_rate:
        if "ra3" not in mutated.planner_config:
            mutated.planner_config["ra3"] = {}

        current = mutated.planner_config["ra3"].get("fallback_threshold", 0.55)
        delta = random.uniform(-0.1, 0.1)
        mutated.planner_config["ra3"]["fallback_threshold"] = max(0.3, min(0.9, current + delta))

    return mutated


def mutate_petri_policy(genome: Genome, mutation_rate: float = 0.1) -> Genome:
    """Mutate PETRI safety policy.

    Args:
        genome: Genome to mutate
        mutation_rate: Probability of mutation

    Returns:
        Mutated genome
    """
    mutated = copy.deepcopy(genome)

    if random.random() < mutation_rate:
        if "petri" not in mutated.executor_config:
            mutated.executor_config["petri"] = {"policy": {}}

        # Adjust risk threshold
        current = mutated.executor_config["petri"].get("risk_threshold", 0.3)
        delta = random.uniform(-0.05, 0.05)
        mutated.executor_config["petri"]["risk_threshold"] = max(0.1, min(0.6, current + delta))

    return mutated


def crossover(parent_a: Genome, parent_b: Genome) -> Genome:
    """Create offspring by combining two parent genomes.

    Args:
        parent_a: First parent
        parent_b: Second parent

    Returns:
        Offspring genome
    """
    import uuid

    offspring = Genome(
        id=str(uuid.uuid4())[:8],
        generation=max(parent_a.generation, parent_b.generation) + 1,
        parent_ids=[parent_a.id, parent_b.id]
    )

    # Mix budgets
    for key in ["latency_ms", "tool_calls", "tokens"]:
        if random.random() < 0.5:
            offspring.budgets[key] = parent_a.budgets[key]
        else:
            offspring.budgets[key] = parent_b.budgets[key]

    # Mix planner config
    if random.random() < 0.5:
        offspring.planner_config = copy.deepcopy(parent_a.planner_config)
    else:
        offspring.planner_config = copy.deepcopy(parent_b.planner_config)

    # Mix executor config
    if random.random() < 0.5:
        offspring.executor_config = copy.deepcopy(parent_a.executor_config)
    else:
        offspring.executor_config = copy.deepcopy(parent_b.executor_config)

    # Inherit best macro library
    if parent_a.fitness > parent_b.fitness:
        offspring.macro_library_id = parent_a.macro_library_id
        offspring.playbook_id = parent_a.playbook_id
    else:
        offspring.macro_library_id = parent_b.macro_library_id
        offspring.playbook_id = parent_b.playbook_id

    return offspring


def mutate(genome: Genome, mutation_rate: float = 0.3) -> Genome:
    """Apply all mutation operators.

    Args:
        genome: Genome to mutate
        mutation_rate: Base mutation rate

    Returns:
        Mutated genome
    """
    mutated = mutate_budgets(genome, mutation_rate)
    mutated = mutate_planner_config(mutated, mutation_rate * 0.7)
    mutated = mutate_petri_policy(mutated, mutation_rate * 0.5)

    # Ensure unique ID for mutant
    import uuid
    mutated.id = str(uuid.uuid4())[:8]
    mutated.generation = genome.generation + 1
    mutated.parent_ids = [genome.id]
    mutated.fitness = 0.0
    mutated.fitness_history = []

    return mutated
