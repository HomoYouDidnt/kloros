"""Flow-GRPO: Group Relative Policy Optimization for episodic reasoning."""
import numpy as np
from typing import List, Dict, Any, Optional
from .dream_types import Genome, FitnessMetrics
from .fitness import evaluate_fitness


class FlowGRPO:
    """Group Relative Policy Optimization for cognitive flows.

    Optimizes genome configurations based on relative performance
    across episodic rollouts.
    """

    def __init__(
        self,
        learning_rate: float = 0.1,
        baseline_momentum: float = 0.9,
        clip_ratio: float = 0.2,
        value_weight: float = 0.5
    ):
        """Initialize Flow-GRPO optimizer.

        Args:
            learning_rate: Step size for updates
            baseline_momentum: Momentum for baseline tracking
            clip_ratio: PPO-style clipping ratio
            value_weight: Weight for value function loss
        """
        self.learning_rate = learning_rate
        self.baseline_momentum = baseline_momentum
        self.clip_ratio = clip_ratio
        self.value_weight = value_weight

        # Baseline tracking
        self.baseline_fitness = 0.0
        self.baseline_latency = 5000.0
        self.baseline_tokens = 3500.0

    def compute_advantages(
        self,
        episode_results: Dict[str, Dict[str, Any]],
        genomes: List[Genome]
    ) -> Dict[str, float]:
        """Compute advantages for each genome relative to group.

        Args:
            episode_results: Results by genome_id
            genomes: List of genomes that were evaluated

        Returns:
            Advantages by genome_id
        """
        # Extract fitness scores
        genome_fitness = {}
        for genome in genomes:
            if genome.id in episode_results:
                result = episode_results[genome.id]
                metrics = evaluate_fitness(result, genome)
                genome_fitness[genome.id] = metrics.fitness

        if not genome_fitness:
            return {}

        # Compute group statistics
        fitnesses = list(genome_fitness.values())
        mean_fitness = np.mean(fitnesses)
        std_fitness = np.std(fitnesses) + 1e-8  # Avoid division by zero

        # Compute standardized advantages
        advantages = {}
        for genome_id, fitness in genome_fitness.items():
            advantage = (fitness - mean_fitness) / std_fitness
            advantages[genome_id] = advantage

        return advantages

    def update_baseline(self, episode_results: Dict[str, Dict[str, Any]]):
        """Update baseline statistics with exponential moving average.

        Args:
            episode_results: Episode results for this batch
        """
        if not episode_results:
            return

        # Collect metrics
        fitnesses = []
        latencies = []
        tokens = []

        for result in episode_results.values():
            if "fitness" in result:
                fitnesses.append(result["fitness"])
            if "latency_ms" in result:
                latencies.append(result["latency_ms"])
            if "tokens" in result:
                tokens.append(result["tokens"])

        # Update baselines
        if fitnesses:
            batch_fitness = np.mean(fitnesses)
            self.baseline_fitness = (
                self.baseline_momentum * self.baseline_fitness +
                (1 - self.baseline_momentum) * batch_fitness
            )

        if latencies:
            batch_latency = np.mean(latencies)
            self.baseline_latency = (
                self.baseline_momentum * self.baseline_latency +
                (1 - self.baseline_momentum) * batch_latency
            )

        if tokens:
            batch_tokens = np.mean(tokens)
            self.baseline_tokens = (
                self.baseline_momentum * self.baseline_tokens +
                (1 - self.baseline_momentum) * batch_tokens
            )

    def compute_policy_updates(
        self,
        genomes: List[Genome],
        advantages: Dict[str, float]
    ) -> Dict[str, Dict[str, Any]]:
        """Compute policy updates for each genome.

        Args:
            genomes: Evaluated genomes
            advantages: Advantages by genome_id

        Returns:
            Updates by genome_id with suggested parameter adjustments
        """
        updates = {}

        for genome in genomes:
            if genome.id not in advantages:
                continue

            advantage = advantages[genome.id]

            # Skip if advantage is too small
            if abs(advantage) < 0.1:
                continue

            update = {
                "advantage": advantage,
                "budget_updates": {},
                "config_updates": {}
            }

            # Budget adjustments based on advantage
            if advantage > 0:
                # Good performance - slightly push budgets in current direction
                # compared to baseline
                if genome.budgets["latency_ms"] < self.baseline_latency:
                    # Faster than baseline, reward by allowing even lower latency
                    update["budget_updates"]["latency_ms"] = int(
                        -self.learning_rate * 200 * advantage
                    )
                if genome.budgets["tokens"] < self.baseline_tokens:
                    # More efficient, reward
                    update["budget_updates"]["tokens"] = int(
                        -self.learning_rate * 100 * advantage
                    )

            elif advantage < 0:
                # Poor performance - adjust toward baseline
                if genome.budgets["latency_ms"] < self.baseline_latency:
                    update["budget_updates"]["latency_ms"] = int(
                        self.learning_rate * 300 * abs(advantage)
                    )
                if genome.budgets["tokens"] < self.baseline_tokens:
                    update["budget_updates"]["tokens"] = int(
                        self.learning_rate * 150 * abs(advantage)
                    )

            # Config adjustments
            if "ra3" in genome.planner_config:
                fallback = genome.planner_config["ra3"].get("fallback_threshold", 0.55)

                if advantage > 0:
                    # Good performance - subtle adjustment
                    update["config_updates"]["ra3_fallback_threshold"] = (
                        fallback + self.learning_rate * 0.02 * advantage
                    )
                elif advantage < 0:
                    # Poor performance - larger adjustment toward default
                    update["config_updates"]["ra3_fallback_threshold"] = (
                        fallback + self.learning_rate * 0.05 * advantage
                    )

            if "petri" in genome.executor_config:
                risk = genome.executor_config["petri"].get("risk_threshold", 0.3)

                if advantage < 0 and genome.stats.get("petri_incidents", 0) > 0:
                    # Poor performance with safety issues - reduce risk threshold
                    update["config_updates"]["petri_risk_threshold"] = (
                        risk - self.learning_rate * 0.05
                    )

            updates[genome.id] = update

        return updates

    def apply_updates(
        self,
        genomes: List[Genome],
        updates: Dict[str, Dict[str, Any]]
    ) -> List[Genome]:
        """Apply policy updates to genomes.

        Args:
            genomes: Genomes to update
            updates: Updates by genome_id

        Returns:
            Updated genomes
        """
        updated = []

        for genome in genomes:
            if genome.id not in updates:
                updated.append(genome)
                continue

            update = updates[genome.id]

            # Apply budget updates
            for key, delta in update.get("budget_updates", {}).items():
                genome.budgets[key] = max(
                    1000,
                    min(10000, genome.budgets[key] + delta)
                )

            # Apply config updates
            config_updates = update.get("config_updates", {})

            if "ra3_fallback_threshold" in config_updates:
                if "ra3" not in genome.planner_config:
                    genome.planner_config["ra3"] = {}
                genome.planner_config["ra3"]["fallback_threshold"] = np.clip(
                    config_updates["ra3_fallback_threshold"],
                    0.3,
                    0.9
                )

            if "petri_risk_threshold" in config_updates:
                if "petri" not in genome.executor_config:
                    genome.executor_config["petri"] = {}
                genome.executor_config["petri"]["risk_threshold"] = np.clip(
                    config_updates["petri_risk_threshold"],
                    0.1,
                    0.6
                )

            updated.append(genome)

        return updated

    def optimize_step(
        self,
        genomes: List[Genome],
        episode_results: Dict[str, Dict[str, Any]]
    ) -> List[Genome]:
        """Perform one optimization step.

        Args:
            genomes: Current genomes
            episode_results: Episode results by genome_id

        Returns:
            Updated genomes
        """
        # Compute advantages
        advantages = self.compute_advantages(episode_results, genomes)

        # Update baseline
        self.update_baseline(episode_results)

        # Compute updates
        updates = self.compute_policy_updates(genomes, advantages)

        # Apply updates
        updated_genomes = self.apply_updates(genomes, updates)

        return updated_genomes

    def get_baseline_stats(self) -> Dict[str, float]:
        """Get current baseline statistics.

        Returns:
            Baseline stats
        """
        return {
            "fitness": self.baseline_fitness,
            "latency_ms": self.baseline_latency,
            "tokens": self.baseline_tokens
        }
