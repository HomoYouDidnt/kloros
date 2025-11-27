"""AgentFlow runner - orchestrates Planner, Executor, Verifier, Generator."""
from typing import Optional
import uuid
import hashlib
from .types import EpisodeRecord, TurnRecord, TaskSpec
from .planner import SimplePlanner
from .executor import Executor
from .verifier import Verifier
from .generator import Generator


class AgentFlowRunner:
    """Orchestrates structured episodic reasoning."""

    def __init__(self, planner: SimplePlanner, executor: Executor,
                 verifier: Verifier, generator: Generator,
                 ace_store=None, config: dict = None):
        """Initialize AgentFlow runner.

        Args:
            planner: Planner instance
            executor: Executor instance
            verifier: Verifier instance
            generator: Generator instance
            ace_store: Optional ACE bullet store
            config: Configuration dict
        """
        self.planner = planner
        self.executor = executor
        self.verifier = verifier
        self.generator = generator
        self.ace_store = ace_store
        self.config = config or {}

    def run_episode(self, task_spec: TaskSpec, kloros_instance=None) -> EpisodeRecord:
        """Run a complete episode.

        Args:
            task_spec: Task specification
            kloros_instance: KLoROS instance for tool execution

        Returns:
            Complete episode record
        """
        episode_id = str(uuid.uuid4())

        # Retrieve ACE hints for this task
        hints = []
        if self.ace_store:
            try:
                bullet_results = self.ace_store.retrieve_bullets(
                    query=task_spec.query,
                    domain=task_spec.domain,
                    k=8
                )
                hints = [b['text'] for b in bullet_results if b.get('distance', 1.0) < 0.5]
                if hints:
                    print(f"[agentflow] Retrieved {len(hints)} ACE hints")
            except Exception as e:
                print(f"[agentflow] Failed to retrieve hints: {e}")

        # Initialize state and turns
        state = {"context": task_spec.query, "domain": task_spec.domain}
        turns = []

        # Execute turns (single-turn for now)
        for turn_idx in range(task_spec.max_turns):
            # Plan
            decision = self.planner.decide(state, task_spec.__dict__, hints=hints)

            # Execute
            exec_result = self.executor.run(decision, state, kloros_instance)

            # Verify
            answer = exec_result.get("artifacts", {}).get("answer", "")
            verify_result = self.verifier.check(exec_result.get("artifacts", {}), answer, task_spec.__dict__)

            # Record turn
            turn = TurnRecord(
                state_fp=self._fingerprint(state),
                decision=decision,
                exec=exec_result,
                verify=verify_result,
                cost={
                    "tokens": exec_result.get("tokens", 0),
                    "latency_ms": exec_result.get("latency", 0),
                    "tool_calls": exec_result.get("tool_calls", 0)
                }
            )
            turns.append(turn)

            # Check if done
            if decision.get("done", True):
                break

        # Generate final answer
        final_answer = self.generator.compose(state, turns[-1].exec.get("artifacts", {}), turns[-1].decision)

        # Create outcome
        outcome = {
            "success": turns[-1].verify.get("pass", False),
            "metrics": turns[-1].verify,
            "final_answer": final_answer
        }

        # Calculate rewards
        trajectory_reward = self._calculate_reward(turns, outcome)
        rewards = {
            "trajectory_R": trajectory_reward,
            "per_turn_A": [trajectory_reward]  # Simple for single-turn
        }

        # Create episode record
        episode = EpisodeRecord(
            episode_id=episode_id,
            task_spec=task_spec.__dict__,
            turns=turns,
            outcome=outcome,
            rewards=rewards,
            safety={"petri_incidents": 0, "blocked_ops": []},
            planner_hints=hints
        )

        # Generate ACE bullets from successful episodes
        if self.ace_store and outcome["success"]:
            try:
                from src.agents.ace.generator import BulletGenerator
                generator = BulletGenerator(self.config.get("ace", {}))
                delta, evidence = generator.propose(episode)

                # Add new bullets
                for bullet in delta.adds:
                    self.ace_store.add_bullet(bullet)
                    print(f"[ace] Added bullet: {bullet.text}")

            except Exception as e:
                print(f"[ace] Failed to generate bullets: {e}")

        return episode

    def _fingerprint(self, state: dict) -> str:
        """Generate state fingerprint.

        Args:
            state: State dict

        Returns:
            Fingerprint string
        """
        state_str = str(sorted(state.items()))
        return hashlib.md5(state_str.encode()).hexdigest()[:12]

    def _calculate_reward(self, turns: list, outcome: dict) -> float:
        """Calculate trajectory reward.

        Args:
            turns: List of turns
            outcome: Episode outcome

        Returns:
            Reward value
        """
        # Simple reward: success - cost penalty
        success_reward = 1.0 if outcome["success"] else 0.0
        score_bonus = outcome.get("metrics", {}).get("score", 0.5)

        # Cost penalties
        total_cost = sum(t.cost.get("latency_ms", 0) for t in turns)
        cost_penalty = min(0.3, total_cost / 10000.0)  # Cap at 0.3

        reward = success_reward + score_bonus - cost_penalty
        return max(0.0, reward)  # Clamp to positive
