"""Committee runner for TUMIX multi-agent reasoning."""
from typing import Dict, Any, List, Callable, Optional
import time
import random
from .types import (
    CommitteeGenome,
    Trial,
    CommitteeRunResult,
    FitnessReport,
    AgentGenome,
    MixGroupResult
)
from .aggregators import aggregate, disagreement_entropy

# Import real agent worker
try:
    from .agent_worker import RealAgentWorker
    REAL_AGENT_AVAILABLE = True
except ImportError:
    REAL_AGENT_AVAILABLE = False


class AgentWorker:
    """Simulated agent worker."""

    def __init__(self, genome: AgentGenome):
        """Initialize agent worker.

        Args:
            genome: Agent genome configuration
        """
        self.genome = genome

    def __call__(self, inputs: Dict[str, Any], comm_state: Dict[str, Any]) -> Dict[str, Any]:
        """Run agent on inputs.

        Args:
            inputs: Task inputs
            comm_state: Communication state from previous rounds

        Returns:
            Output dict with answer, confidence, trace, tool counts
        """
        # Simulated agent execution
        # In production, this would call actual planning/execution pipeline

        task_query = inputs.get("query", inputs.get("task", ""))

        # Simple simulated reasoning based on genome config
        answer = f"Answer from {self.genome.id}"
        confidence = 0.5 + random.random() * 0.3  # 0.5-0.8

        # Adjust confidence based on genome config
        if self.genome.depth > 1:
            confidence += 0.1
        if self.genome.reflection_steps > 0:
            confidence += 0.05

        confidence = min(0.95, confidence)

        trace = f"Used {self.genome.planner} planner with depth={self.genome.depth}"

        tool_counts = {}
        for tool, enabled in self.genome.tools.items():
            if enabled:
                tool_counts[tool] = random.randint(0, 2)

        return {
            "output": {
                "answer": answer,
                "confidence": confidence,
                "trace": trace
            },
            "tool_counts": tool_counts,
            "latency_ms": random.randint(100, self.genome.latency_budget_ms)
        }


class CommitteeRunner:
    """Runs TUMIX committee-based reasoning."""

    def __init__(
        self,
        cost_weights: Optional[Dict[str, float]] = None,
        judge_pool: Optional[Any] = None,
        use_real_agents: bool = False,
        agentflow_runner: Optional[Any] = None
    ):
        """Initialize committee runner.

        Args:
            cost_weights: Weights for cost components (latency, tool)
            judge_pool: Optional pool of judge agents
            use_real_agents: Use real AgentFlow agents instead of simulated
            agentflow_runner: Optional shared AgentFlowRunner for all agents
        """
        self.cost_weights = cost_weights or {"latency": 0.05, "tool": 0.02}
        self.judge_pool = judge_pool
        self.use_real_agents = use_real_agents and REAL_AGENT_AVAILABLE
        self.agentflow_runner = agentflow_runner

        if self.use_real_agents and not REAL_AGENT_AVAILABLE:
            print("[committee] Warning: Real agents requested but not available, using simulated")
            self.use_real_agents = False

    def run(
        self,
        committee: CommitteeGenome,
        trials: List[Trial],
        rounds: Optional[int] = None
    ) -> tuple[Any, FitnessReport]:
        """Run committee on trials.

        Args:
            committee: CommitteeGenome configuration
            trials: List of trials to run
            rounds: Optional override for communication rounds

        Returns:
            (best_artifact, fitness_report)
        """
        R = rounds or committee.comms_rounds
        fitness_accum = []
        artifacts = []

        for trial in trials:
            result = self._run_one(committee, trial, R)
            fitness = self._score(committee, trial, result)
            fitness_accum.append(fitness)
            artifacts.append(result.aggregated_output)

        # Aggregate fitness across trials
        if not fitness_accum:
            return None, FitnessReport(
                score=0.0,
                components={},
                stability={},
                intra_similarity=0.0
            )

        avg_score = sum(f.score for f in fitness_accum) / len(fitness_accum)

        # Return best artifact by per-trial score
        best_idx = max(range(len(fitness_accum)), key=lambda i: fitness_accum[i].score)

        # Aggregate components
        avg_components = {}
        for key in fitness_accum[0].components:
            avg_components[key] = sum(f.components.get(key, 0) for f in fitness_accum) / len(fitness_accum)

        avg_stability = {}
        for key in fitness_accum[0].stability:
            avg_stability[key] = sum(f.stability.get(key, 0) for f in fitness_accum) / len(fitness_accum)

        avg_similarity = sum(f.intra_similarity for f in fitness_accum) / len(fitness_accum)

        return artifacts[best_idx], FitnessReport(
            score=avg_score,
            components=avg_components,
            stability=avg_stability,
            intra_similarity=avg_similarity
        )

    def _run_one(
        self,
        committee: CommitteeGenome,
        trial: Trial,
        rounds: int
    ) -> CommitteeRunResult:
        """Run committee on one trial.

        Args:
            committee: CommitteeGenome configuration
            trial: Trial to run
            rounds: Number of communication rounds

        Returns:
            CommitteeRunResult
        """
        # Initialize workers (real or simulated)
        if self.use_real_agents:
            workers = [
                RealAgentWorker(member, self.agentflow_runner)
                for member in committee.members[:committee.k]
            ]
        else:
            workers = [AgentWorker(member) for member in committee.members[:committee.k]]

        # Round loop with communication
        comm_state = {}
        per_agent_outputs = {}
        tool_counts: Dict[str, int] = {}
        total_latency = 0

        for r in range(rounds):
            # Parallel execution (simulated sequentially)
            for worker in workers:
                output = worker(trial.inputs, comm_state)

                agent_id = worker.genome.id
                per_agent_outputs[agent_id] = output["output"]

                # Accumulate tool counts
                for tool, count in output["tool_counts"].items():
                    tool_counts[tool] = tool_counts.get(tool, 0) + count

                total_latency += output["latency_ms"]

                # Update communication state
                comm_state[agent_id] = {
                    "rationale": output["output"].get("trace", ""),
                    "answer": output["output"].get("answer", "")
                }

        # Aggregation
        agg_output, votes = aggregate(
            committee.aggregation,
            committee,
            per_agent_outputs,
            comm_state,
            self.judge_pool
        )

        return CommitteeRunResult(
            committee_id=committee.id,
            task_id=trial.task_id,
            votes=votes,
            outputs_by_agent=per_agent_outputs,
            aggregated_output=agg_output,
            tools_used=tool_counts,
            latency_ms=total_latency,
            diag={
                "entropy": disagreement_entropy(votes),
                "rounds": rounds
            }
        )

    def _score(
        self,
        committee: CommitteeGenome,
        trial: Trial,
        result: CommitteeRunResult
    ) -> FitnessReport:
        """Score committee result.

        Args:
            committee: CommitteeGenome configuration
            trial: Trial
            result: CommitteeRunResult

        Returns:
            FitnessReport
        """
        # Use real evaluation if using real agents
        if self.use_real_agents:
            return self._score_real(committee, trial, result)

        # Simulated evaluation (fallback)
        # Accuracy (simulated)
        acc = 0.6 + random.random() * 0.3  # 0.6-0.9

        # Consistency (bootstrap agreement - simulated)
        boot = 0.7 + random.random() * 0.2  # 0.7-0.9

        # Robustness (perturbation stability - simulated)
        pert = 0.65 + random.random() * 0.25  # 0.65-0.9

        # Similarity (collapse check - simulated)
        sim = 0.3 + random.random() * 0.3  # 0.3-0.6

        # Cost
        cost = (
            self.cost_weights["latency"] * (result.latency_ms / 1000.0) +
            self.cost_weights["tool"] * sum(result.tools_used.values())
        )

        # Fitness weights
        w = {
            "acc": 0.65,
            "consistency": 0.15,
            "robust": 0.10,
            "cost": 0.05,
            "collapse": 0.05
        }

        score = (
            w["acc"] * acc +
            w["consistency"] * boot +
            w["robust"] * pert -
            w["cost"] * cost -
            w["collapse"] * sim
        )

        return FitnessReport(
            score=score,
            components={
                "acc": acc,
                "consistency": boot,
                "robust": pert,
                "cost": -cost,
                "collapse": -sim
            },
            stability={
                "bootstrap_agree": boot,
                "perturb_delta": pert
            },
            intra_similarity=sim
        )

    def _score_real(
        self,
        committee: CommitteeGenome,
        trial: Trial,
        result: CommitteeRunResult
    ) -> FitnessReport:
        """Score committee result using real evaluation.

        Args:
            committee: CommitteeGenome configuration
            trial: Trial
            result: CommitteeRunResult

        Returns:
            FitnessReport
        """
        from src.agents.agentflow.verifier import Verifier

        verifier = Verifier()

        # Get all agent scores
        agent_scores = []
        for agent_id, output in result.outputs_by_agent.items():
            answer = output.get("answer", output.get("output", ""))
            artifacts = output.get("artifacts", {})

            # Verify each agent's output
            verify_result = verifier.check(artifacts, answer, trial.inputs)
            agent_scores.append(verify_result.get("score", 0.0))

        # Accuracy: average of agent scores
        acc = sum(agent_scores) / len(agent_scores) if agent_scores else 0.0

        # Consistency: variance in scores (lower variance = higher consistency)
        if len(agent_scores) > 1:
            mean_score = sum(agent_scores) / len(agent_scores)
            variance = sum((s - mean_score) ** 2 for s in agent_scores) / len(agent_scores)
            boot = max(0.0, 1.0 - variance)  # Invert variance to consistency
        else:
            boot = 1.0

        # Robustness: minimum score (weakest link)
        pert = min(agent_scores) if agent_scores else 0.0

        # Similarity: check if all agents gave similar answers (collapse detection)
        unique_answers = set()
        for output in result.outputs_by_agent.values():
            answer = str(output.get("answer", output.get("output", "")))
            unique_answers.add(answer.lower().strip())

        # High similarity (collapse) if < 2 unique answers
        sim = 1.0 - (len(unique_answers) / len(result.outputs_by_agent)) if result.outputs_by_agent else 0.0

        # Cost
        cost = (
            self.cost_weights["latency"] * (result.latency_ms / 1000.0) +
            self.cost_weights["tool"] * sum(result.tools_used.values())
        )

        # Fitness weights
        w = {
            "acc": 0.65,
            "consistency": 0.15,
            "robust": 0.10,
            "cost": 0.05,
            "collapse": 0.05
        }

        score = (
            w["acc"] * acc +
            w["consistency"] * boot +
            w["robust"] * pert -
            w["cost"] * cost -
            w["collapse"] * sim
        )

        return FitnessReport(
            score=score,
            components={
                "acc": acc,
                "consistency": boot,
                "robust": pert,
                "cost": -cost,
                "collapse": -sim
            },
            stability={
                "bootstrap_agree": boot,
                "perturb_delta": pert
            },
            intra_similarity=sim
        )


class SimpleTUMIXRunner:
    """Simplified TUMIX runner for evolutionary composition."""

    def __init__(
        self,
        test_fn: Callable[[Any], Dict[str, Any]],
        compose_fn: Callable[[List[Any]], Any],
        score_fn: Callable[[Dict[str, Any]], float],
        group_size: int = 3,
        groups: int = 3,
        rounds: int = 2,
        diversity_bias: float = 0.5
    ):
        """Initialize TUMIX runner.

        Args:
            test_fn: Function to test an approach
            compose_fn: Function to compose multiple approaches
            score_fn: Function to score test results
            group_size: Size of each group
            groups: Number of groups
            rounds: Number of composition rounds
            diversity_bias: Diversity bias for grouping
        """
        self.test_fn = test_fn
        self.compose_fn = compose_fn
        self.score_fn = score_fn
        self.group_size = group_size
        self.groups = groups
        self.rounds = rounds
        self.diversity_bias = diversity_bias

    def run(self, approaches: List[Any]) -> Dict[str, Any]:
        """Run TUMIX on approaches.

        Args:
            approaches: List of approaches to mix

        Returns:
            Result dict with winning approach and metrics
        """
        # 1) Form groups
        buckets = self._form_groups(approaches)

        # 2) Intra-group play
        champs = []
        for group in buckets:
            champ = self._play_group(group)
            champs.append(champ)

        # 3) Tournament across group champions
        if not champs:
            return {"approach": approaches[0] if approaches else None, "metrics": {}}

        final = self._tournament([c["approach"] for c in champs])
        return final

    def _form_groups(self, approaches: List[Any]) -> List[List[Any]]:
        """Form groups from approaches.

        Args:
            approaches: List of approaches

        Returns:
            List of groups (list of approaches)
        """
        shuffled = approaches[:]
        random.shuffle(shuffled)

        k = min(self.groups * self.group_size, len(shuffled))
        trimmed = shuffled[:k]

        return [
            trimmed[i:i + self.group_size]
            for i in range(0, len(trimmed), self.group_size)
        ]

    def _play_group(self, group: List[Any]) -> Dict[str, Any]:
        """Play group (intra-group composition).

        Args:
            group: List of approaches in group

        Returns:
            Champion dict with approach, metrics, lineage
        """
        pool = group[:]
        lineage = {id(a): [a] for a in pool}

        for _ in range(self.rounds):
            candidates = []

            for i in range(len(pool)):
                for j in range(i + 1, len(pool)):
                    composed = self.compose_fn([pool[i], pool[j]])
                    res = self.test_fn(composed)
                    candidates.append((composed, res, [pool[i], pool[j]]))

            if not candidates:
                break

            # Select best by score
            best = max(candidates, key=lambda x: self.score_fn(x[1]))
            pool = [best[0]]
            lineage[id(best[0])] = lineage.get(id(best[0]), []) + best[2]

        # Return champion
        if not pool:
            return {"approach": group[0], "metrics": {}, "lineage": []}

        final_res = self.test_fn(pool[0])
        return {
            "approach": pool[0],
            "metrics": final_res,
            "lineage": [id(a) for a in lineage.get(id(pool[0]), [])]
        }

    def _tournament(self, champs: List[Any]) -> Dict[str, Any]:
        """Run tournament among champions.

        Args:
            champs: List of champion approaches

        Returns:
            Winner dict with approach and metrics
        """
        if len(champs) == 1:
            return {"approach": champs[0], "metrics": self.test_fn(champs[0])}

        best = None
        best_score = float("-inf")

        for approach in champs:
            res = self.test_fn(approach)
            score = self.score_fn(res)

            if score > best_score:
                best = {"approach": approach, "metrics": res}
                best_score = score

        return best if best else {"approach": champs[0], "metrics": {}}
