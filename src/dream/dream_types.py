"""D-REAM type definitions."""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass
class Genome:
    """Represents a complete cognitive system configuration."""

    id: str
    generation: int = 0

    # Component configurations
    planner_config: Dict[str, Any] = field(default_factory=dict)
    executor_config: Dict[str, Any] = field(default_factory=dict)
    verifier_config: Dict[str, Any] = field(default_factory=dict)

    # RA³ macro library
    macro_library_id: Optional[str] = None

    # ACE playbook
    playbook_id: Optional[str] = None

    # Budgets
    budgets: Dict[str, Any] = field(default_factory=lambda: {
        "latency_ms": 5000,
        "tool_calls": 4,
        "tokens": 3500
    })

    # Fitness metrics
    fitness: float = 0.0
    fitness_history: List[float] = field(default_factory=list)

    # Performance stats
    stats: Dict[str, Any] = field(default_factory=lambda: {
        "episodes": 0,
        "successes": 0,
        "failures": 0,
        "avg_latency_ms": 0.0,
        "avg_tokens": 0.0,
        "petri_incidents": 0
    })

    # Lineage
    parent_ids: List[str] = field(default_factory=list)
    created_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().timestamp()


@dataclass
class Population:
    """Population of genomes for evolution."""

    generation: int
    genomes: List[Genome]
    best_genome: Optional[Genome] = None
    best_fitness: float = 0.0

    # Population stats
    avg_fitness: float = 0.0
    fitness_std: float = 0.0

    def update_stats(self):
        """Update population statistics."""
        if not self.genomes:
            return

        fitnesses = [g.fitness for g in self.genomes]
        self.avg_fitness = sum(fitnesses) / len(fitnesses)

        # Calculate std dev
        variance = sum((f - self.avg_fitness) ** 2 for f in fitnesses) / len(fitnesses)
        self.fitness_std = variance ** 0.5

        # Find best genome
        best = max(self.genomes, key=lambda g: g.fitness)
        if best.fitness > self.best_fitness:
            self.best_genome = best
            self.best_fitness = best.fitness


@dataclass
class FitnessMetrics:
    """Fitness evaluation metrics."""

    genome_id: str
    generation: int

    # Core metrics
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    avg_tokens: float = 0.0

    # Safety
    petri_incidents: int = 0
    petri_blocks: int = 0

    # Quality
    verifier_score: float = 0.0
    user_feedback: float = 0.0

    # Computed fitness
    fitness: float = 0.0

    # Episode count
    episodes: int = 0

    def compute_fitness(self, weights: Optional[Dict[str, float]] = None) -> float:
        """Compute overall fitness score.

        Args:
            weights: Weight configuration for different metrics

        Returns:
            Fitness score (higher is better)
        """
        weights = weights or {
            "success": 0.6,
            "latency": -0.2,  # Negative because lower is better
            "tokens": -0.1,
            "safety": -0.7,  # Strong penalty for safety issues
            "verifier": 0.3,
            "user": 0.4
        }

        fitness = 0.0

        # Success component
        fitness += weights["success"] * self.success_rate

        # Latency component (normalize to seconds, penalty for high latency)
        latency_penalty = min(1.0, self.avg_latency_ms / 5000.0)
        fitness += weights["latency"] * latency_penalty

        # Token cost component (normalize to thousands)
        token_penalty = min(1.0, self.avg_tokens / 3500.0)
        fitness += weights["tokens"] * token_penalty

        # Safety component (strong penalty)
        if self.petri_incidents > 0:
            fitness += weights["safety"]

        # Quality components
        fitness += weights["verifier"] * self.verifier_score
        fitness += weights["user"] * self.user_feedback

        self.fitness = max(0.0, fitness)  # Clamp to non-negative
        return self.fitness
