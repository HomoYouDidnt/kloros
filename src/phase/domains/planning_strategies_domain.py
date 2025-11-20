"""PHASE Domain: Planning Strategies Benchmark

Compares planning strategies head-to-head (fast_coder, reAct, deep_planner, etc.)
with ground truth verification, robustness testing, and full audit trails.

Metrics:
- Accuracy (vs ground truth)
- Latency (p50, p95, p99)
- Token cost
- Robustness (adversarial prompt variants)
- Tool efficiency (fewer tools, same accuracy = bonus)

Outputs fitness scores for D-REAM consumption via bandit allocation.
"""

import json
import time
import hashlib
import random
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)

# Fitness output path for D-REAM
FITNESS_OUTPUT = "/home/kloros/var/dream/fitness/planning_strategies.jsonl"


@dataclass
class PlanningStrategyTrial:
    """A single trial with ground truth and audit trail."""
    task_id: str
    task_prompt: str
    ground_truth: Any  # Oracle answer for verification
    robustness_variants: List[str]  # Adversarial edits for robustness testing

    # Determinism audit trail (REQUIRED)
    seed: int
    model_hash: str  # Hash of model configuration
    tool_set_snapshot: List[str]  # Available tools at test time
    mcp_manifest_version: str  # MCP manifest version

    # Strategy outputs
    strategy_outputs: Dict[str, Any]  # {strategy_name: output}
    strategy_latencies: Dict[str, int]  # {strategy_name: latency_ms}
    strategy_costs: Dict[str, float]  # {strategy_name: token_cost}
    strategy_tools_used: Dict[str, int]  # {strategy_name: tool_count}

    # Fitness scores (0-1, higher = better)
    fitness_scores: Dict[str, float]


class PlanningStrategiesDomain:
    """PHASE domain for benchmarking planning strategies.

    Runs head-to-head comparisons with:
    - Ground truth verification (not "seems right")
    - Robustness testing (adversarial prompt edits)
    - Full audit logs (seed, model hash, tool set, manifest version)
    - UCB1 bandit allocation (budget shifts to winner)
    """

    def __init__(self):
        """Initialize planning strategies domain."""
        self.trials: List[PlanningStrategyTrial] = []
        self.strategies = ["fast_coder", "reAct", "deep_planner"]

        # UCB1 bandit state
        self.strategy_pulls = {s: 0 for s in self.strategies}
        self.strategy_rewards = {s: 0.0 for s in self.strategies}

        # Ensure output directory exists
        Path(FITNESS_OUTPUT).parent.mkdir(parents=True, exist_ok=True)

    def _create_test_suite(self) -> List[Dict[str, Any]]:
        """Create test suite with ground truth.

        Returns:
            List of test tasks with oracle answers
        """
        return [
            {
                "task_id": "coding_01",
                "prompt": "Write a Python function that checks if a number is prime",
                "ground_truth": {
                    "contains": ["def is_prime", "if n <= 1", "return False", "for i in range"],
                    "correctness": "function returns True for primes, False for non-primes"
                },
                "variants": [
                    "Write a Python function to check primality",
                    "Create a Python function that determines if a number is prime"
                ]
            },
            {
                "task_id": "reasoning_01",
                "prompt": "If Alice is taller than Bob, and Bob is taller than Carol, who is shortest?",
                "ground_truth": {"answer": "Carol", "reasoning": "transitive relation"},
                "variants": [
                    "Alice > Bob > Carol. Who is the shortest?",
                    "Given Alice is taller than Bob, and Bob is taller than Carol, identify the shortest person"
                ]
            },
            {
                "task_id": "multi_step_01",
                "prompt": "First read the file /tmp/data.txt, then count the words, then return the count",
                "ground_truth": {"steps": ["read_file", "count_words", "return_count"], "order": "sequential"},
                "variants": [
                    "Read /tmp/data.txt, count words, and return the total",
                    "Task: 1) Read /tmp/data.txt 2) Count words 3) Return count"
                ]
            }
        ]

    def _get_model_hash(self) -> str:
        """Get hash of current model configuration.

        Returns:
            MD5 hash of model config
        """
        # Placeholder - replace with actual model config
        config = {"model": "claude-sonnet-4", "version": "20250929"}
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()[:8]

    def _get_tool_snapshot(self) -> List[str]:
        """Get snapshot of available tools.

        Returns:
            List of tool names
        """
        try:
            from src.mcp.integration import MCPIntegration
            mcp = MCPIntegration(enable_discovery=False)
            # Load from registry
            from src.registry.loader import get_registry
            registry = get_registry()
            caps = registry.get_enabled_capabilities()
            return [c.name for c in caps]
        except Exception as e:
            logger.warning("[planning_strategies] Tool snapshot failed: %s", e)
            return []

    def _get_mcp_manifest_version(self) -> str:
        """Get MCP manifest version.

        Returns:
            Manifest version string
        """
        manifest_file = Path("/home/kloros/src/mcp/manifests/deepagents.yaml")
        if manifest_file.exists():
            try:
                import yaml
                with open(manifest_file) as f:
                    manifest = yaml.safe_load(f)
                    return manifest.get("version", "unknown")
            except:
                pass
        return "1.0.0"  # Default

    def _run_strategy(
        self,
        strategy: str,
        task_prompt: str,
        seed: int
    ) -> Tuple[Any, int, float, int]:
        """Run a planning strategy on a task.

        Args:
            strategy: Strategy name (fast_coder, reAct, deep_planner)
            task_prompt: Task prompt
            seed: Random seed

        Returns:
            Tuple of (output, latency_ms, token_cost, tools_used)
        """
        # Placeholder implementation - replace with actual strategy execution
        random.seed(seed)
        start_time = time.time()

        # Simulate strategy execution
        if strategy == "deep_planner":
            time.sleep(random.uniform(0.05, 0.15))  # Slower but higher quality
            quality = random.uniform(0.7, 0.95)
            tools_used = random.randint(2, 5)
            token_cost = random.uniform(1000, 3000)
        elif strategy == "fast_coder":
            time.sleep(random.uniform(0.01, 0.05))  # Faster but lower quality
            quality = random.uniform(0.5, 0.8)
            tools_used = random.randint(1, 3)
            token_cost = random.uniform(300, 1000)
        else:  # reAct
            time.sleep(random.uniform(0.03, 0.10))
            quality = random.uniform(0.6, 0.85)
            tools_used = random.randint(2, 4)
            token_cost = random.uniform(500, 1500)

        latency_ms = int((time.time() - start_time) * 1000)

        output = {
            "answer": f"[{strategy}] Solution (quality={quality:.2f})",
            "confidence": quality,
            "strategy": strategy
        }

        return output, latency_ms, token_cost, tools_used

    def _verify_ground_truth(self, output: Any, ground_truth: Dict) -> float:
        """Verify output against ground truth (oracle).

        Args:
            output: Strategy output
            ground_truth: Oracle answer

        Returns:
            Accuracy score (0-1)
        """
        # Placeholder - replace with actual verification
        # For now, use simulated quality from output
        if isinstance(output, dict) and "confidence" in output:
            return output["confidence"]
        return 0.5

    def _test_robustness(
        self,
        strategy: str,
        original_output: Any,
        variants: List[str],
        seed: int
    ) -> float:
        """Test robustness with adversarial prompt variants.

        Args:
            strategy: Strategy name
            original_output: Output on original prompt
            variants: Adversarial prompt variants
            seed: Random seed

        Returns:
            Robustness score (0-1, higher = more robust)
        """
        # Run strategy on variants
        variant_outputs = []
        for variant in variants:
            output, _, _, _ = self._run_strategy(strategy, variant, seed)
            variant_outputs.append(output)

        # Check consistency (placeholder - use actual similarity)
        # For now, assume 80% robustness
        return 0.8

    def _calculate_fitness(
        self,
        strategy: str,
        trial: PlanningStrategyTrial
    ) -> float:
        """Calculate fitness score for strategy on trial.

        Components:
        - Accuracy (0.5 weight)
        - Latency (0.2 weight, normalized)
        - Cost (0.2 weight, normalized)
        - Tool efficiency (0.1 weight)

        Args:
            strategy: Strategy name
            trial: Trial data

        Returns:
            Fitness score (0-1, higher = better)
        """
        output = trial.strategy_outputs.get(strategy)
        latency = trial.strategy_latencies.get(strategy, 9999)
        cost = trial.strategy_costs.get(strategy, 9999.0)
        tools_used = trial.strategy_tools_used.get(strategy, 10)

        # Accuracy
        accuracy = self._verify_ground_truth(output, trial.ground_truth)

        # Latency (normalize: lower is better, max 30s)
        latency_score = max(0.0, 1.0 - (latency / 30000.0))

        # Cost (normalize: lower is better, max 5000 tokens)
        cost_score = max(0.0, 1.0 - (cost / 5000.0))

        # Tool efficiency (fewer tools = better, max 10)
        tool_score = max(0.0, 1.0 - (tools_used / 10.0))

        # Weighted fitness
        fitness = (
            accuracy * 0.5 +
            latency_score * 0.2 +
            cost_score * 0.2 +
            tool_score * 0.1
        )

        return round(fitness, 3)

    def run_single_epoch_test(
        self,
        epoch_id: str,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """Run single epoch of planning strategies benchmark.

        Args:
            epoch_id: Epoch identifier
            seed: Random seed (for determinism)

        Returns:
            Epoch results with fitness scores
        """
        if seed is None:
            seed = int(time.time())

        random.seed(seed)

        # Get audit trail components
        model_hash = self._get_model_hash()
        tool_snapshot = self._get_tool_snapshot()
        manifest_version = self._get_mcp_manifest_version()

        # Create test suite
        test_suite = self._create_test_suite()

        logger.info(
            "[planning_strategies] Starting epoch '%s' with %d tasks, seed=%d",
            epoch_id, len(test_suite), seed
        )

        # Run all strategies on all tasks
        for task in test_suite:
            trial = PlanningStrategyTrial(
                task_id=task["task_id"],
                task_prompt=task["prompt"],
                ground_truth=task["ground_truth"],
                robustness_variants=task["variants"],
                seed=seed,
                model_hash=model_hash,
                tool_set_snapshot=tool_snapshot,
                mcp_manifest_version=manifest_version,
                strategy_outputs={},
                strategy_latencies={},
                strategy_costs={},
                strategy_tools_used={},
                fitness_scores={}
            )

            # Run each strategy
            for strategy in self.strategies:
                output, latency, cost, tools = self._run_strategy(
                    strategy, task["prompt"], seed
                )

                trial.strategy_outputs[strategy] = output
                trial.strategy_latencies[strategy] = latency
                trial.strategy_costs[strategy] = cost
                trial.strategy_tools_used[strategy] = tools

                # Calculate fitness
                fitness = self._calculate_fitness(strategy, trial)
                trial.fitness_scores[strategy] = fitness

                # Update UCB1 bandit
                self.strategy_pulls[strategy] += 1
                self.strategy_rewards[strategy] += fitness

            self.trials.append(trial)

        # Aggregate results
        avg_fitness = {
            strategy: (
                self.strategy_rewards[strategy] / self.strategy_pulls[strategy]
                if self.strategy_pulls[strategy] > 0 else 0.0
            )
            for strategy in self.strategies
        }

        # Write fitness to D-REAM
        self._write_fitness(epoch_id, avg_fitness)

        # Calculate UCB1 allocations
        total_pulls = sum(self.strategy_pulls.values())
        ucb1_allocations = self._calculate_ucb1_allocations(total_pulls)

        logger.info(
            "[planning_strategies] Epoch complete. Fitness: %s",
            avg_fitness
        )

        return {
            "epoch_id": epoch_id,
            "tasks_run": len(test_suite),
            "strategies": self.strategies,
            "avg_fitness": avg_fitness,
            "ucb1_allocations": ucb1_allocations,
            "winner": max(avg_fitness, key=avg_fitness.get),
            "audit": {
                "seed": seed,
                "model_hash": model_hash,
                "tools_count": len(tool_snapshot),
                "manifest_version": manifest_version
            }
        }

    def _calculate_ucb1_allocations(self, total_pulls: int) -> Dict[str, float]:
        """Calculate UCB1 budget allocations.

        Args:
            total_pulls: Total pulls across all strategies

        Returns:
            Dict of {strategy: allocation_fraction}
        """
        import math

        ucb1_scores = {}
        for strategy in self.strategies:
            pulls = self.strategy_pulls[strategy]
            if pulls == 0:
                ucb1_scores[strategy] = float('inf')  # Explore untried strategies
            else:
                avg_reward = self.strategy_rewards[strategy] / pulls
                exploration = math.sqrt(2 * math.log(total_pulls) / pulls)
                ucb1_scores[strategy] = avg_reward + exploration

        # Normalize to allocations (softmax-like)
        total_score = sum(ucb1_scores.values())
        if total_score == 0:
            return {s: 1.0 / len(self.strategies) for s in self.strategies}

        allocations = {
            strategy: round(score / total_score, 3)
            for strategy, score in ucb1_scores.items()
        }

        return allocations

    def _write_fitness(self, epoch_id: str, fitness_scores: Dict[str, float]):
        """Write fitness scores to D-REAM consumption file.

        Args:
            epoch_id: Epoch identifier
            fitness_scores: {strategy: fitness}
        """
        fitness_entry = {
            "timestamp": time.time(),
            "epoch_id": epoch_id,
            "domain": "planning_strategies",
            "strategies": fitness_scores
        }

        with open(FITNESS_OUTPUT, 'a') as f:
            f.write(json.dumps(fitness_entry) + '\n')

        logger.info("[planning_strategies] Wrote fitness to %s", FITNESS_OUTPUT)


def run_planning_strategies_benchmark(epoch_id: str = None) -> Dict[str, Any]:
    """Run planning strategies benchmark (main entry point).

    Args:
        epoch_id: Optional epoch ID (auto-generated if None)

    Returns:
        Benchmark results
    """
    if epoch_id is None:
        epoch_id = f"planning_bench_{int(time.time())}"

    domain = PlanningStrategiesDomain()
    return domain.run_single_epoch_test(epoch_id)


if __name__ == "__main__":
    # Standalone test
    results = run_planning_strategies_benchmark()
    print(json.dumps(results, indent=2))
