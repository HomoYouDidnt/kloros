#!/usr/bin/env python3
"""
Genetic Algorithm for Hyperparameter Search
Implements population-based optimization for D-REAM hyperparameter tuning.
"""
import random
import json
import copy
from typing import List, Dict, Any, Tuple


class HyperparameterGA:
    """
    Genetic Algorithm for hyperparameter optimization.

    Uses tournament selection, uniform crossover, and Gaussian mutation
    to evolve high-performing hyperparameter configurations.
    """

    def __init__(
        self,
        param_space: Dict[str, Dict[str, Any]],
        population_size: int = 8,
        elite_count: int = 2,
        mutation_rate: float = 0.3,
        tournament_size: int = 3
    ):
        """
        Initialize genetic algorithm.

        Args:
            param_space: Dictionary defining parameter ranges and types
                Example: {
                    "beam": {"type": "int", "min": 1, "max": 5},
                    "vad_threshold": {"type": "float", "min": 0.2, "max": 0.6},
                    "temperature": {"type": "float", "min": 0.0, "max": 1.0}
                }
            population_size: Number of candidates per generation
            elite_count: Number of top performers to preserve unchanged
            mutation_rate: Probability of mutating each parameter (0.0-1.0)
            tournament_size: Number of candidates in tournament selection
        """
        self.param_space = param_space
        self.population_size = population_size
        self.elite_count = elite_count
        self.mutation_rate = mutation_rate
        self.tournament_size = tournament_size

        # Track evolution history
        self.generation = 0
        self.fitness_history = []
        self.best_individual = None
        self.best_fitness = -float('inf')

    def initialize_population(self) -> List[Dict[str, Any]]:
        """Generate initial random population."""
        population = []
        for _ in range(self.population_size):
            individual = {}
            for param_name, param_config in self.param_space.items():
                individual[param_name] = self._random_value(param_config)
            population.append(individual)
        return population

    def _random_value(self, param_config: Dict[str, Any]) -> Any:
        """Generate random value within parameter constraints."""
        param_type = param_config["type"]

        if param_type == "int":
            return random.randint(param_config["min"], param_config["max"])
        elif param_type == "float":
            return random.uniform(param_config["min"], param_config["max"])
        elif param_type == "choice":
            return random.choice(param_config["values"])
        else:
            raise ValueError(f"Unknown parameter type: {param_type}")

    def tournament_selection(
        self,
        population: List[Dict[str, Any]],
        fitness_scores: List[float]
    ) -> Dict[str, Any]:
        """
        Select individual using tournament selection.

        Randomly picks tournament_size individuals and returns the best one.
        """
        tournament_indices = random.sample(range(len(population)), self.tournament_size)
        tournament_fitness = [fitness_scores[i] for i in tournament_indices]
        winner_idx = tournament_indices[tournament_fitness.index(max(tournament_fitness))]
        return copy.deepcopy(population[winner_idx])

    def crossover(
        self,
        parent1: Dict[str, Any],
        parent2: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Uniform crossover: randomly mix parameters from two parents.

        For each parameter, randomly choose from parent1 or parent2.
        """
        child1 = {}
        child2 = {}

        for param_name in self.param_space.keys():
            if random.random() < 0.5:
                child1[param_name] = parent1[param_name]
                child2[param_name] = parent2[param_name]
            else:
                child1[param_name] = parent2[param_name]
                child2[param_name] = parent1[param_name]

        return child1, child2

    def mutate(self, individual: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply Gaussian mutation to individual.

        Each parameter has mutation_rate probability of being mutated.
        - For floats: Add Gaussian noise (±10% of range)
        - For ints: Add/subtract random amount (1-2)
        - For choices: Randomly pick new value
        """
        mutated = copy.deepcopy(individual)

        for param_name, param_config in self.param_space.items():
            if random.random() < self.mutation_rate:
                param_type = param_config["type"]

                if param_type == "float":
                    # Gaussian noise: ±10% of parameter range
                    param_range = param_config["max"] - param_config["min"]
                    noise = random.gauss(0, param_range * 0.1)
                    mutated[param_name] = max(
                        param_config["min"],
                        min(param_config["max"], mutated[param_name] + noise)
                    )

                elif param_type == "int":
                    # Random walk: ±1 or ±2
                    delta = random.choice([-2, -1, 1, 2])
                    mutated[param_name] = max(
                        param_config["min"],
                        min(param_config["max"], mutated[param_name] + delta)
                    )

                elif param_type == "choice":
                    # Random new choice
                    mutated[param_name] = random.choice(param_config["values"])

        return mutated

    def evolve(
        self,
        population: List[Dict[str, Any]],
        fitness_scores: List[float]
    ) -> List[Dict[str, Any]]:
        """
        Evolve population to next generation.

        Uses elitism + selection + crossover + mutation.
        """
        # Sort population by fitness (descending)
        sorted_pop = [ind for _, ind in sorted(
            zip(fitness_scores, population),
            key=lambda x: x[0],
            reverse=True
        )]
        sorted_fitness = sorted(fitness_scores, reverse=True)

        # Track best individual
        if sorted_fitness[0] > self.best_fitness:
            self.best_fitness = sorted_fitness[0]
            self.best_individual = copy.deepcopy(sorted_pop[0])

        # Store fitness history
        self.fitness_history.append({
            "generation": self.generation,
            "best": sorted_fitness[0],
            "mean": sum(fitness_scores) / len(fitness_scores),
            "worst": sorted_fitness[-1]
        })

        # Build next generation
        next_generation = []

        # Elitism: Keep top performers
        for i in range(self.elite_count):
            next_generation.append(copy.deepcopy(sorted_pop[i]))

        # Generate rest through selection + crossover + mutation
        while len(next_generation) < self.population_size:
            # Select parents
            parent1 = self.tournament_selection(population, fitness_scores)
            parent2 = self.tournament_selection(population, fitness_scores)

            # Crossover
            child1, child2 = self.crossover(parent1, parent2)

            # Mutation
            child1 = self.mutate(child1)
            child2 = self.mutate(child2)

            # Add to next generation (up to population size)
            next_generation.append(child1)
            if len(next_generation) < self.population_size:
                next_generation.append(child2)

        self.generation += 1
        return next_generation

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of GA evolution."""
        return {
            "generation": self.generation,
            "population_size": self.population_size,
            "best_fitness": self.best_fitness,
            "best_individual": self.best_individual,
            "fitness_history": self.fitness_history
        }


# Default hyperparameter search space for ASR/TTS
DEFAULT_ASR_TTS_SPACE = {
    "beam": {"type": "int", "min": 1, "max": 5},
    "vad_threshold": {"type": "float", "min": 0.25, "max": 0.60},
    "temperature": {"type": "float", "min": 0.0, "max": 0.5},
    "max_initial_timestamp": {"type": "float", "min": 0.0, "max": 1.0},
    "no_speech_threshold": {"type": "float", "min": 0.3, "max": 0.8}
}


def run_genetic_search(
    param_space: Dict[str, Dict[str, Any]],
    fitness_function: callable,
    num_generations: int = 5,
    population_size: int = 8,
    elite_count: int = 2
) -> Dict[str, Any]:
    """
    Run genetic algorithm hyperparameter search.

    Args:
        param_space: Dictionary defining parameter ranges
        fitness_function: Function that takes params dict and returns fitness score
        num_generations: Number of generations to evolve
        population_size: Number of candidates per generation
        elite_count: Number of top performers to preserve

    Returns:
        Dictionary with results including best individual and fitness history
    """
    ga = HyperparameterGA(
        param_space=param_space,
        population_size=population_size,
        elite_count=elite_count
    )

    # Initialize population
    population = ga.initialize_population()

    all_evaluated = []  # Track all evaluated individuals

    for gen in range(num_generations):
        import sys
        print(f"[GA] Generation {gen + 1}/{num_generations}", file=sys.stderr, flush=True)

        # Evaluate fitness for each individual
        fitness_scores = []
        for individual in population:
            fitness = fitness_function(individual)
            fitness_scores.append(fitness)

            # Track for reporting
            all_evaluated.append({
                "generation": gen + 1,
                "params": individual,
                "fitness": fitness
            })

        # Print generation stats
        best_fitness = max(fitness_scores)
        mean_fitness = sum(fitness_scores) / len(fitness_scores)
        print(f"[GA]   Best: {best_fitness:.3f}  Mean: {mean_fitness:.3f}", file=sys.stderr, flush=True)

        # Evolve to next generation (except on last generation)
        if gen < num_generations - 1:
            population = ga.evolve(population, fitness_scores)

    # Final summary
    summary = ga.get_summary()
    summary["all_evaluated"] = all_evaluated

    return summary


if __name__ == "__main__":
    # Test with dummy fitness function
    def dummy_fitness(params):
        """Dummy fitness: prefer higher beam and moderate VAD threshold."""
        return params["beam"] * 0.2 + (0.4 - abs(params["vad_threshold"] - 0.4)) * 0.5

    results = run_genetic_search(
        param_space=DEFAULT_ASR_TTS_SPACE,
        fitness_function=dummy_fitness,
        num_generations=3,
        population_size=6
    )

    print("\n=== Genetic Algorithm Results ===")
    print(f"Best Fitness: {results['best_fitness']:.3f}")
    print(f"Best Individual: {json.dumps(results['best_individual'], indent=2)}")
    print(f"\nFitness History:")
    for gen_stats in results['fitness_history']:
        print(f"  Gen {gen_stats['generation']}: "
              f"Best={gen_stats['best']:.3f}, "
              f"Mean={gen_stats['mean']:.3f}, "
              f"Worst={gen_stats['worst']:.3f}")
