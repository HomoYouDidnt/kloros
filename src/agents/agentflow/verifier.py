"""Verifier component for AgentFlow - checks execution quality."""
from typing import Dict, Any, Optional


class Verifier:
    """Verifies execution results and provides quality scores."""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize verifier.

        Args:
            config: Configuration dict
        """
        self.config = config or {}

    def check(self, artifacts: Dict[str, Any], answer: Optional[str],
              task_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Verify execution results.

        Args:
            artifacts: Execution artifacts
            answer: Final answer string
            task_spec: Original task specification

        Returns:
            Verification result with pass/fail, score, critique
        """
        # Simple heuristic verification
        errors = artifacts.get("errors", []) if isinstance(artifacts, dict) else []

        # Check for execution success
        has_answer = bool(answer or artifacts.get("answer"))
        no_errors = len(errors) == 0

        # Calculate score (0.0 - 1.0)
        score = 0.0
        if has_answer:
            score += 0.5
        if no_errors:
            score += 0.3
        if answer and len(str(answer)) > 10:
            score += 0.2

        passed = score >= 0.5

        # Generate critique
        if passed:
            critique = f"Execution successful (score: {score:.2f})"
        else:
            critique = f"Execution suboptimal (score: {score:.2f})"
            if not has_answer:
                critique += " - No answer produced"
            if errors:
                critique += f" - {len(errors)} errors"

        return {
            "pass": passed,
            "score": score,
            "critique": critique,
            "errors": errors
        }
