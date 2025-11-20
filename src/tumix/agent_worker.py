"""Real agent worker that integrates with AgentFlow."""
from typing import Dict, Any
import time
from .types import AgentGenome


class RealAgentWorker:
    """Real agent worker using AgentFlow planner/executor."""

    def __init__(self, genome: AgentGenome, agentflow_runner=None):
        """Initialize real agent worker.

        Args:
            genome: Agent genome configuration
            agentflow_runner: AgentFlowRunner instance (will create if None)
        """
        self.genome = genome

        # Initialize AgentFlow components if not provided
        if agentflow_runner is None:
            from src.agentflow.planner import SimplePlanner
            from src.agentflow.executor import Executor
            from src.agentflow.verifier import Verifier
            from src.agentflow.generator import Generator
            from src.agentflow.runner import AgentFlowRunner

            # Configure based on genome
            config = {
                "ra3": {"enabled": False},  # Can be enabled per genome
                "petri": {"enabled": False},  # Can be enabled per genome
            }

            # Create components
            planner = SimplePlanner(config=config)

            # Set executor budgets from genome
            budgets = {
                "latency_ms": genome.latency_budget_ms,
                "tool_calls": genome.depth * 2,  # Approximate
                "tokens": 3500
            }
            executor = Executor(budgets=budgets)

            verifier = Verifier(config=config)
            generator = Generator()

            # Create runner
            self.runner = AgentFlowRunner(
                planner=planner,
                executor=executor,
                verifier=verifier,
                generator=generator,
                config=config
            )
        else:
            self.runner = agentflow_runner

    def __call__(self, inputs: Dict[str, Any], comm_state: Dict[str, Any]) -> Dict[str, Any]:
        """Run agent on inputs using real AgentFlow.

        Args:
            inputs: Task inputs
            comm_state: Communication state from previous rounds

        Returns:
            Output dict with answer, confidence, trace, tool counts
        """
        from src.agentflow.types import TaskSpec

        # Extract task info
        query = inputs.get("query", inputs.get("task", ""))
        domain = inputs.get("domain", "general")

        # Create task spec (note: TaskSpec doesn't have task_id field)
        task_spec = TaskSpec(
            query=query,
            domain=domain,
            max_turns=self.genome.depth
        )

        # Run episode through AgentFlow
        start_time = time.time()
        try:
            episode = self.runner.run_episode(task_spec, kloros_instance=None)

            # Extract results
            final_turn = episode.turns[-1] if episode.turns else None

            if final_turn:
                answer = episode.outcome.get("final_answer", "")
                confidence = final_turn.verify.get("score", 0.5)
                trace = final_turn.decision.get("rationale", "")

                # Extract tool usage
                tool_counts = {}
                for turn in episode.turns:
                    tool = turn.decision.get("tool", "unknown")
                    tool_counts[tool] = tool_counts.get(tool, 0) + 1

                latency_ms = int((time.time() - start_time) * 1000)

                return {
                    "output": {
                        "answer": answer,
                        "confidence": confidence,
                        "trace": trace,
                        "artifacts": final_turn.exec.get("artifacts", {})
                    },
                    "tool_counts": tool_counts,
                    "latency_ms": latency_ms,
                    "episode": episode  # Include full episode for analysis
                }
            else:
                # Empty episode
                return {
                    "output": {
                        "answer": "",
                        "confidence": 0.0,
                        "trace": "No turns executed"
                    },
                    "tool_counts": {},
                    "latency_ms": int((time.time() - start_time) * 1000)
                }

        except Exception as e:
            # Error during execution
            return {
                "output": {
                    "answer": "",
                    "confidence": 0.0,
                    "trace": f"Error: {str(e)}"
                },
                "tool_counts": {},
                "latency_ms": int((time.time() - start_time) * 1000),
                "error": str(e)
            }
