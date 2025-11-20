"""
D-REAM Tool Evolution

Evolutionary optimization for synthesized tools that fail promotion gates.
Uses genetic programming to improve tool code quality, performance, and safety.
"""
from __future__ import annotations
import json
import hashlib
import random
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ToolGenome:
    """Represents a tool variant in the evolutionary population."""
    tool_name: str
    version: str  # Semantic version
    code: str
    analysis: Dict[str, Any]
    generation: int
    fitness: float = 0.0
    parent_versions: List[str] = None
    mutations: List[str] = None

    def __post_init__(self):
        if self.parent_versions is None:
            self.parent_versions = []
        if self.mutations is None:
            self.mutations = []

    def compute_hash(self) -> str:
        """Compute hash of tool code for versioning."""
        return hashlib.sha256(self.code.encode()).hexdigest()[:8]


class ToolEvolver:
    """
    Evolutionary optimizer for synthesized tools.

    Applies mutations to improve:
    - Performance (latency, resource usage)
    - Safety (error handling, validation)
    - Code quality (readability, maintainability)
    """

    def __init__(self, llm_backend=None):
        """
        Initialize tool evolver.

        Args:
            llm_backend: LLM backend for code generation
        """
        self.llm_backend = llm_backend
        self.evolution_dir = Path("/home/kloros/.kloros/dream/tool_evolution")
        self.evolution_dir.mkdir(parents=True, exist_ok=True)

        # Evolution parameters
        self.population_size = 8
        self.max_generations = 5
        self.mutation_rate = 0.7
        self.crossover_rate = 0.3
        self.elite_count = 2

    def evolve_tool(
        self,
        tool_name: str,
        initial_code: str,
        analysis: Dict[str, Any],
        failure_reason: str,
        shadow_stats: Optional[Dict] = None
    ) -> Optional[ToolGenome]:
        """
        Evolve a tool through multiple generations to improve fitness.

        Args:
            tool_name: Name of tool to evolve
            initial_code: Initial tool implementation
            analysis: Tool analysis metadata
            failure_reason: Why promotion failed
            shadow_stats: Shadow test statistics if available

        Returns:
            Best evolved tool genome or None if evolution failed
        """
        print(f"[dream] Starting evolution of {tool_name}")
        print(f"[dream] Failure reason: {failure_reason}")

        # Create initial population
        population = self._create_initial_population(
            tool_name, initial_code, analysis, failure_reason
        )

        best_genome = None

        for gen in range(self.max_generations):
            print(f"[dream] Generation {gen + 1}/{self.max_generations}")

            # Evaluate fitness
            for genome in population:
                genome.fitness = self._evaluate_fitness(genome, shadow_stats)

            # Sort by fitness
            population.sort(key=lambda g: g.fitness, reverse=True)

            # Track best
            if population[0].fitness > (best_genome.fitness if best_genome else 0):
                best_genome = population[0]
                print(f"[dream] New best: {best_genome.version} (fitness: {best_genome.fitness:.3f})")

            # Early stopping if good enough
            if best_genome and best_genome.fitness > 0.8:
                print(f"[dream] Early stopping: fitness threshold reached")
                break

            # Create next generation
            if gen < self.max_generations - 1:
                population = self._create_next_generation(population)

        # Save evolution history
        self._save_evolution_history(tool_name, population, best_genome)

        return best_genome

    def _create_initial_population(
        self,
        tool_name: str,
        initial_code: str,
        analysis: Dict,
        failure_reason: str
    ) -> List[ToolGenome]:
        """Create initial population with mutations of base tool."""
        population = []

        # Add original as baseline
        base_genome = ToolGenome(
            tool_name=tool_name,
            version="0.1.0",
            code=initial_code,
            analysis=analysis,
            generation=0,
            fitness=0.0
        )
        population.append(base_genome)

        # Generate variants through targeted mutations
        for i in range(self.population_size - 1):
            mutated_code = self._apply_targeted_mutation(
                initial_code, failure_reason, analysis
            )

            if mutated_code and mutated_code != initial_code:
                genome = ToolGenome(
                    tool_name=tool_name,
                    version=f"0.1.{i + 1}",
                    code=mutated_code,
                    analysis=analysis,
                    generation=0,
                    parent_versions=["0.1.0"],
                    mutations=[f"targeted_fix_{i}"]
                )
                population.append(genome)

        return population

    def _apply_targeted_mutation(
        self,
        code: str,
        failure_reason: str,
        analysis: Dict
    ) -> Optional[str]:
        """Apply targeted mutation based on failure reason."""

        # Pattern-based mutations for common issues
        if "not_winning_enough" in failure_reason:
            # Performance optimization mutations
            mutations = [
                self._optimize_imports,
                self._add_caching,
                self._optimize_loops,
                self._reduce_api_calls,
            ]
        elif "tests_red" in failure_reason:
            # Correctness mutations
            mutations = [
                self._add_error_handling,
                self._fix_edge_cases,
                self._add_input_validation,
                self._improve_return_types,
            ]
        elif "risk_blocked" in failure_reason:
            # Safety mutations
            mutations = [
                self._add_safety_checks,
                self._sandbox_side_effects,
                self._add_logging,
                self._reduce_permissions,
            ]
        else:
            # General improvements
            mutations = [
                self._improve_readability,
                self._add_docstrings,
                self._optimize_performance,
            ]

        # Apply random mutation
        mutation_fn = random.choice(mutations)
        try:
            mutated = mutation_fn(code, analysis)
            return mutated if mutated else code
        except Exception as e:
            print(f"[dream] Mutation failed: {e}")
            return code

    def _optimize_imports(self, code: str, analysis: Dict) -> str:
        """Optimize imports to reduce load time."""
        lines = code.split('\n')

        # Move imports inside functions if not used at module level
        optimized = []
        for line in lines:
            if line.strip().startswith('import ') or line.strip().startswith('from '):
                # Check if used at module level
                module = line.split()[1].split('.')[0]
                module_level_use = any(
                    module in l and not l.strip().startswith('import')
                    for l in lines if l.strip() and not l.strip().startswith('#')
                )
                if not module_level_use:
                    continue  # Skip, will add inside function
            optimized.append(line)

        return '\n'.join(optimized)

    def _add_error_handling(self, code: str, analysis: Dict) -> str:
        """Add comprehensive error handling."""
        # Find function definition
        lines = code.split('\n')
        func_start = -1
        for i, line in enumerate(lines):
            if line.strip().startswith('def '):
                func_start = i
                break

        if func_start == -1:
            return code

        # Wrap function body in try-except
        indent = '    '
        try_block = []
        try_block.append(lines[func_start])  # def line

        # Find docstring end
        body_start = func_start + 1
        if '"""' in lines[func_start + 1]:
            # Find end of docstring
            for i in range(func_start + 2, len(lines)):
                if '"""' in lines[i]:
                    body_start = i + 1
                    break

        # Add try
        try_block.extend(lines[func_start + 1:body_start])
        try_block.append(f'{indent}try:')

        # Indent existing body
        for line in lines[body_start:]:
            if line.strip():
                try_block.append(f'    {line}')
            else:
                try_block.append(line)

        # Add except
        try_block.append(f'{indent}except Exception as e:')
        try_block.append(f'{indent}    return f"Error: {{e}}"')

        return '\n'.join(try_block)

    def _add_caching(self, code: str, analysis: Dict) -> str:
        """Add result caching for expensive operations."""
        # Simple memoization pattern
        if '@cache' in code or '_cache' in code:
            return code  # Already has caching

        cached_version = "from functools import lru_cache\n\n@lru_cache(maxsize=128)\n" + code
        return cached_version

    def _add_safety_checks(self, code: str, analysis: Dict) -> str:
        """Add safety checks for high-risk operations."""
        lines = code.split('\n')
        safe_lines = []

        for line in lines:
            # Add validation before risky operations
            if 'os.system(' in line or 'subprocess.run(' in line:
                indent = len(line) - len(line.lstrip())
                safe_lines.append(' ' * indent + '# Safety: validate command')
                safe_lines.append(' ' * indent + 'if not _is_safe_command(cmd):')
                safe_lines.append(' ' * indent + '    return "Unsafe operation blocked"')

            safe_lines.append(line)

        return '\n'.join(safe_lines)

    def _optimize_loops(self, code: str, analysis: Dict) -> str:
        """Optimize loops for better performance."""
        # Convert simple for loops to list comprehensions where applicable
        return code  # Placeholder

    def _reduce_api_calls(self, code: str, analysis: Dict) -> str:
        """Reduce redundant API calls."""
        return code  # Placeholder

    def _fix_edge_cases(self, code: str, analysis: Dict) -> str:
        """Add handling for edge cases."""
        return code  # Placeholder

    def _add_input_validation(self, code: str, analysis: Dict) -> str:
        """Add input parameter validation."""
        return code  # Placeholder

    def _improve_return_types(self, code: str, analysis: Dict) -> str:
        """Ensure consistent return types."""
        return code  # Placeholder

    def _sandbox_side_effects(self, code: str, analysis: Dict) -> str:
        """Sandbox side effects with dry-run mode."""
        return code  # Placeholder

    def _add_logging(self, code: str, analysis: Dict) -> str:
        """Add logging for debugging."""
        return code  # Placeholder

    def _reduce_permissions(self, code: str, analysis: Dict) -> str:
        """Reduce required permissions."""
        return code  # Placeholder

    def _improve_readability(self, code: str, analysis: Dict) -> str:
        """Improve code readability."""
        return code  # Placeholder

    def _add_docstrings(self, code: str, analysis: Dict) -> str:
        """Add comprehensive docstrings."""
        return code  # Placeholder

    def _optimize_performance(self, code: str, analysis: Dict) -> str:
        """General performance optimizations."""
        return code  # Placeholder

    def _evaluate_fitness(
        self,
        genome: ToolGenome,
        shadow_stats: Optional[Dict] = None
    ) -> float:
        """
        Evaluate fitness of tool genome.

        Fitness components:
        - Code quality (complexity, readability)
        - Safety (error handling, validation)
        - Performance (estimated from code analysis)
        - Shadow test results (if available)
        """
        fitness = 0.5  # Base fitness

        code = genome.code

        # Code quality checks
        if 'try:' in code and 'except' in code:
            fitness += 0.15  # Error handling

        if '"""' in code or "'''" in code:
            fitness += 0.05  # Docstrings

        if 'logging' in code or 'print(' in code:
            fitness += 0.05  # Observability

        # Safety checks
        if 'if ' in code and 'return' in code:
            fitness += 0.10  # Input validation

        # Penalize dangerous patterns
        if 'eval(' in code or 'exec(' in code:
            fitness -= 0.3

        if 'os.system' in code:
            fitness -= 0.2

        # Complexity penalty
        line_count = len([l for l in code.split('\n') if l.strip()])
        if line_count > 100:
            fitness -= 0.1  # Too complex

        # Shadow test results
        if shadow_stats:
            if shadow_stats.get('avg_delta', 0) > 0:
                fitness += min(shadow_stats['avg_delta'] * 2, 0.3)

            if shadow_stats.get('trials', 0) > 0:
                success_rate = shadow_stats.get('wins', 0) / shadow_stats['trials']
                fitness += success_rate * 0.2

        return max(0.0, min(1.0, fitness))

    def _create_next_generation(self, population: List[ToolGenome]) -> List[ToolGenome]:
        """Create next generation through selection, crossover, mutation."""
        next_gen = []

        # Elitism: keep best genomes
        next_gen.extend(population[:self.elite_count])

        # Fill rest through crossover and mutation
        while len(next_gen) < self.population_size:
            if random.random() < self.crossover_rate and len(population) >= 2:
                # Crossover
                parent1 = random.choice(population[:len(population) // 2])
                parent2 = random.choice(population[:len(population) // 2])
                child = self._crossover(parent1, parent2)
            else:
                # Mutation
                parent = random.choice(population[:len(population) // 2])
                child = self._mutate(parent)

            if child:
                next_gen.append(child)

        return next_gen[:self.population_size]

    def _crossover(self, parent1: ToolGenome, parent2: ToolGenome) -> Optional[ToolGenome]:
        """Combine code from two parents."""
        # Simple: take first half from parent1, second half from parent2
        lines1 = parent1.code.split('\n')
        lines2 = parent2.code.split('\n')

        split = len(lines1) // 2
        child_code = '\n'.join(lines1[:split] + lines2[split:])

        gen = max(parent1.generation, parent2.generation) + 1

        return ToolGenome(
            tool_name=parent1.tool_name,
            version=f"0.{gen}.0",
            code=child_code,
            analysis=parent1.analysis,
            generation=gen,
            parent_versions=[parent1.version, parent2.version],
            mutations=["crossover"]
        )

    def _mutate(self, parent: ToolGenome) -> Optional[ToolGenome]:
        """Apply random mutation to parent."""
        mutated_code = self._apply_targeted_mutation(
            parent.code,
            "general_improvement",
            parent.analysis
        )

        if not mutated_code or mutated_code == parent.code:
            return None

        gen = parent.generation + 1

        return ToolGenome(
            tool_name=parent.tool_name,
            version=f"0.{gen}.0",
            code=mutated_code,
            analysis=parent.analysis,
            generation=gen,
            parent_versions=[parent.version],
            mutations=["random_mutation"]
        )

    def _save_evolution_history(
        self,
        tool_name: str,
        population: List[ToolGenome],
        best: Optional[ToolGenome]
    ):
        """Save evolution history for analysis."""
        history = {
            "tool_name": tool_name,
            "timestamp": datetime.now().isoformat(),
            "population_size": len(population),
            "generations": max(g.generation for g in population) + 1,
            "best_fitness": best.fitness if best else 0.0,
            "best_version": best.version if best else None,
            "population_fitness": [g.fitness for g in population],
        }

        history_file = self.evolution_dir / f"{tool_name}_evolution.json"
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)

        # Save best genome code
        if best:
            code_file = self.evolution_dir / f"{tool_name}_best_{best.version}.py"
            with open(code_file, 'w') as f:
                f.write(best.code)
