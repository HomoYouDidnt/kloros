"""TUMIX Deep Planner Worker

Bridges DeepAgents to TUMIX committee system for voting and comparison.
"""

from typing import Dict, Any
import logging
from .types import AgentGenome

logger = logging.getLogger(__name__)


class DeepPlannerWorker:
    """TUMIX worker for DeepAgents deep planner.

    Wraps DeepAgents to participate in committee voting alongside
    fast_coder, reAct, and other planning strategies.

    Parameters:
        genome: AgentGenome with planner="deep_planner"
        mcp_integration: MCPIntegration instance for tool discovery

    Example:
        >>> genome = AgentGenome(id="deep1", planner="deep_planner")
        >>> worker = DeepPlannerWorker(genome, mcp_integration=mcp)
        >>> result = worker(inputs, comm_state)
    """

    def __init__(self, genome: AgentGenome, mcp_integration=None):
        """Initialize deep planner worker.

        Args:
            genome: Agent genome configuration
            mcp_integration: MCP integration for tool discovery
        """
        if genome.planner != "deep_planner":
            raise ValueError(
                f"DeepPlannerWorker requires planner='deep_planner', "
                f"got '{genome.planner}'"
            )

        self.genome = genome
        self.mcp_integration = mcp_integration

        # Create DeepAgents worker
        from src.agents.deepagents.wrapper import DeepAgentsWorker, DeepAgentsConfig

        config = DeepAgentsConfig(
            timeout_ms=genome.latency_budget_ms,
            hard_kill_ms=int(genome.latency_budget_ms * 1.5),  # 1.5x for hard kill
            mcp_integration=mcp_integration,
            enable_vfs=True,
            vfs_cleanup=True
        )

        self.deepagents_worker = DeepAgentsWorker(config)

        logger.info(
            "[tumix.deep_planner] Initialized worker for genome '%s'",
            genome.id
        )

    def __call__(self, inputs: Dict[str, Any], comm_state: Dict[str, Any]) -> Dict[str, Any]:
        """Run deep planner on inputs.

        Args:
            inputs: Task inputs (query, domain, etc.)
            comm_state: Communication state from previous rounds

        Returns:
            TUMIX-compatible output dict:
                - output: {answer, confidence, trace, artifacts}
                - tool_counts: Tool usage histogram
                - latency_ms: Execution time
        """
        logger.info(
            "[tumix.deep_planner] Running for genome '%s' on task",
            self.genome.id
        )

        try:
            # Run DeepAgents worker
            result = self.deepagents_worker(inputs, comm_state)

            logger.info(
                "[tumix.deep_planner] Completed in %dms (genome '%s')",
                result["latency_ms"],
                self.genome.id
            )

            return result

        except Exception as e:
            logger.error(
                "[tumix.deep_planner] Failed for genome '%s': %s",
                self.genome.id,
                e
            )

            # Return error result
            return {
                "output": {
                    "answer": "",
                    "confidence": 0.0,
                    "trace": f"Error: {str(e)}",
                    "artifacts": {}
                },
                "tool_counts": {},
                "latency_ms": 0,
                "error": str(e)
            }


def create_deep_planner_worker(genome: AgentGenome, **kwargs) -> DeepPlannerWorker:
    """Factory function for creating deep planner workers.

    Args:
        genome: AgentGenome configuration
        **kwargs: Additional arguments (mcp_integration, etc.)

    Returns:
        DeepPlannerWorker instance
    """
    return DeepPlannerWorker(genome, **kwargs)
