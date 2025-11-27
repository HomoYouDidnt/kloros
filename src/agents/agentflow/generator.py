"""Generator component for AgentFlow - composes final answers."""
from typing import Dict, Any


class Generator:
    """Generates final answers from execution artifacts."""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize generator.

        Args:
            config: Configuration dict
        """
        self.config = config or {}

    def compose(self, state: Dict[str, Any], artifacts: Dict[str, Any],
                decision: Dict[str, Any]) -> str:
        """Compose final answer from artifacts.

        Args:
            state: Current state
            artifacts: Execution artifacts
            decision: Original decision

        Returns:
            Final answer string
        """
        # Extract answer from artifacts
        if "answer" in artifacts:
            return str(artifacts["answer"])

        # Fallback: compose from available data
        if artifacts:
            return f"Executed {decision.get('tool', 'unknown')}: {artifacts}"

        return "No answer generated"
