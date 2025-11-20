"""D-REAM evolution engine."""
import random
import copy
from typing import List, Optional, Callable, Dict, Any
from .dream_types import Genome, Population, FitnessMetrics
from .mutations import mutate, crossover
from .fitness import evaluate_fitness


class EvolutionEngine:
    """Manages evolutionary optimization of cognitive system configurations."""

    def __init__(
        self,
        population_size: int = 20,
        elite_size: int = 3,
        mutation_rate: float = 0.3,
        tournament_size: int = 3,
        fitness_evaluator: Optional[Callable] = None
    ):
        """Initialize evolution engine.

        Args:
            population_size: Number of genomes in population
            elite_size: Number of top genomes to preserve
            mutation_rate: Base mutation rate
            tournament_size: Size of tournament for selection
            fitness_evaluator: Custom fitness evaluation function
        """
        self.population_size = population_size
        self.elite_size = elite_size
        self.mutation_rate = mutation_rate
        self.tournament_size = tournament_size
        self.fitness_evaluator = fitness_evaluator or evaluate_fitness

        self.current_population: Optional[Population] = None
        self.generation = 0

    def initialize_population(self, seed_genome: Genome) -> Population:
        """Create initial population from seed genome.

        Args:
            seed_genome: Base genome to mutate from

        Returns:
            Initial population
        """
        genomes = [seed_genome]

        # Create variants through mutation
        for i in range(self.population_size - 1):
            variant = mutate(seed_genome, mutation_rate=self.mutation_rate)
            variant.id = f"gen0_{i:03d}"
            genomes.append(variant)

        population = Population(
            generation=0,
            genomes=genomes
        )
        population.update_stats()

        self.current_population = population
        self.generation = 0

        return population

    def tournament_select(self, population: Population) -> Genome:
        """Select genome using tournament selection.

        Args:
            population: Current population

        Returns:
            Selected genome
        """
        tournament = random.sample(population.genomes, self.tournament_size)
        winner = max(tournament, key=lambda g: g.fitness)
        return winner

    def select_parents(self, population: Population, n_pairs: int) -> List[tuple]:
        """Select parent pairs for breeding.

        Args:
            population: Current population
            n_pairs: Number of parent pairs to select

        Returns:
            List of (parent_a, parent_b) tuples
        """
        pairs = []
        for _ in range(n_pairs):
            parent_a = self.tournament_select(population)
            parent_b = self.tournament_select(population)
            pairs.append((parent_a, parent_b))
        return pairs

    def breed_offspring(self, parent_a: Genome, parent_b: Genome) -> Genome:
        """Create offspring from two parents.

        Args:
            parent_a: First parent
            parent_b: Second parent

        Returns:
            Offspring genome (already mutated)
        """
        # Crossover
        offspring = crossover(parent_a, parent_b)

        # Mutation
        offspring = mutate(offspring, mutation_rate=self.mutation_rate)

        return offspring

    def evolve_generation(self, episode_results: Dict[str, Any]) -> Population:
        """Evolve population for one generation.

        Args:
            episode_results: Results from evaluating current generation
                Format: {genome_id: {"success": bool, "latency_ms": int, ...}}

        Returns:
            Next generation population
        """
        if self.current_population is None:
            raise ValueError("Population not initialized")

        # Update fitness for all genomes
        for genome in self.current_population.genomes:
            if genome.id in episode_results:
                result = episode_results[genome.id]
                metrics = self.fitness_evaluator(result, genome)
                genome.fitness = metrics.fitness
                genome.fitness_history.append(metrics.fitness)

                # Update stats
                genome.stats["episodes"] += 1
                if result.get("success", False):
                    genome.stats["successes"] += 1
                else:
                    genome.stats["failures"] += 1
                genome.stats["avg_latency_ms"] = result.get("latency_ms", 0)
                genome.stats["avg_tokens"] = result.get("tokens", 0)
                if result.get("petri_blocked", False):
                    genome.stats["petri_incidents"] += 1

        self.current_population.update_stats()

        # Sort by fitness
        sorted_genomes = sorted(
            self.current_population.genomes,
            key=lambda g: g.fitness,
            reverse=True
        )

        # Elitism: preserve top genomes
        next_generation = sorted_genomes[:self.elite_size]

        # Breed offspring to fill rest of population
        n_offspring = self.population_size - self.elite_size
        parent_pairs = self.select_parents(self.current_population, n_offspring)

        for i, (parent_a, parent_b) in enumerate(parent_pairs):
            offspring = self.breed_offspring(parent_a, parent_b)
            offspring.id = f"gen{self.generation + 1}_{i:03d}"
            next_generation.append(offspring)

        # Create new population
        new_population = Population(
            generation=self.generation + 1,
            genomes=next_generation
        )
        new_population.update_stats()

        self.current_population = new_population
        self.generation += 1

        return new_population

    def get_best_genome(self) -> Optional[Genome]:
        """Get the best genome from current population.

        Returns:
            Best genome or None if no population
        """
        if self.current_population is None:
            return None

        return self.current_population.best_genome

    def export_population(self) -> Dict[str, Any]:
        """Export current population state.

        Returns:
            Population state as dict
        """
        if self.current_population is None:
            return {}

        return {
            "generation": self.generation,
            "population_size": self.population_size,
            "best_fitness": self.current_population.best_fitness,
            "avg_fitness": self.current_population.avg_fitness,
            "fitness_std": self.current_population.fitness_std,
            "genomes": [
                {
                    "id": g.id,
                    "fitness": g.fitness,
                    "fitness_history": g.fitness_history,
                    "generation": g.generation,
                    "parent_ids": g.parent_ids,
                    "budgets": g.budgets,
                    "planner_config": g.planner_config,
                    "executor_config": g.executor_config,
                    "stats": g.stats
                }
                for g in self.current_population.genomes
            ]
        }

    def import_population(self, state: Dict[str, Any]) -> Population:
        """Import population from exported state.

        Args:
            state: Population state dict

        Returns:
            Restored population
        """
        genomes = []
        for g_data in state["genomes"]:
            genome = Genome(
                id=g_data["id"],
                generation=g_data["generation"],
                parent_ids=g_data["parent_ids"],
                budgets=g_data["budgets"],
                planner_config=g_data["planner_config"],
                executor_config=g_data["executor_config"],
                fitness=g_data["fitness"],
                fitness_history=g_data["fitness_history"],
                stats=g_data["stats"]
            )
            genomes.append(genome)

        population = Population(
            generation=state["generation"],
            genomes=genomes
        )
        population.update_stats()

        self.current_population = population
        self.generation = state["generation"]

        return population
