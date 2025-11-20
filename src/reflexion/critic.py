"""Reflexion critic for self-improvement through critique."""
from typing import Dict, Any, List, Optional
from .schema import as_note


class Critic:
    """Critic that reviews task outputs and provides feedback."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize critic.

        Args:
            config: Optional configuration
        """
        self.config = config or {}
        self.critique_history: List[Dict[str, Any]] = []

    def review(
        self,
        task_spec: Dict[str, Any],
        state: Dict[str, Any],
        draft: Any,
        artifacts: Dict[str, Any],
        verifier: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Review a draft and provide critique.

        Args:
            task_spec: Task specification
            state: Current state
            draft: Draft output
            artifacts: Artifacts produced
            verifier: Verifier results

        Returns:
            Critique note dict
        """
        # If verifier passed, no critique needed
        if verifier.get("pass", False):
            return as_note("Looks good", "", 0.0)

        # Analyze failure patterns
        verifier_score = verifier.get("score", 0.0)
        errors = verifier.get("errors", [])
        warnings = verifier.get("warnings", [])

        # Generate critique based on failure mode
        if verifier_score < 0.3:
            # Severe failure - suggest major changes
            return self._critique_severe_failure(task_spec, state, draft, artifacts, verifier)
        elif verifier_score < 0.6:
            # Moderate failure - suggest improvements
            return self._critique_moderate_failure(task_spec, state, draft, artifacts, verifier)
        else:
            # Minor issues - suggest refinements
            return self._critique_minor_issues(task_spec, state, draft, artifacts, verifier)

    def _critique_severe_failure(
        self,
        task_spec: Dict[str, Any],
        state: Dict[str, Any],
        draft: Any,
        artifacts: Dict[str, Any],
        verifier: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Critique severe failure.

        Args:
            task_spec: Task specification
            state: Current state
            draft: Draft output
            artifacts: Artifacts
            verifier: Verifier results

        Returns:
            Critique note
        """
        # Check if wrong tool was used
        tools_used = artifacts.get("tools_used", [])
        task_type = task_spec.get("type", "")

        if task_type == "math" and "search" in tools_used and "code" not in tools_used:
            return as_note(
                "Wrong tool for math task",
                "prefer_code_exec",
                0.9,
                ["tool_choice"],
                "Prefer code.exec before search in math tasks"
            )

        if task_type == "code" and not tools_used:
            return as_note(
                "No tools used for code task",
                "use_code_tools",
                0.85,
                ["tool_usage"],
                "Always use code execution tools for programming tasks"
            )

        # Generic severe failure
        return as_note(
            "Severe failure - approach fundamentally wrong",
            "rethink_strategy",
            0.8,
            ["approach"],
            None
        )

    def _critique_moderate_failure(
        self,
        task_spec: Dict[str, Any],
        state: Dict[str, Any],
        draft: Any,
        artifacts: Dict[str, Any],
        verifier: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Critique moderate failure.

        Args:
            task_spec: Task specification
            state: Current state
            draft: Draft output
            artifacts: Artifacts
            verifier: Verifier results

        Returns:
            Critique note
        """
        errors = verifier.get("errors", [])

        # Check for common error patterns
        if any("syntax" in str(e).lower() for e in errors):
            return as_note(
                "Syntax errors in output",
                "validate_syntax",
                0.75,
                ["syntax"],
                "Always validate syntax before submission"
            )

        if any("timeout" in str(e).lower() for e in errors):
            return as_note(
                "Execution timeout",
                "optimize_performance",
                0.7,
                ["performance"],
                "Optimize algorithms to avoid timeouts"
            )

        # Generic moderate failure
        return as_note(
            "Moderate issues - needs refinement",
            "refine_approach",
            0.65,
            ["quality"],
            None
        )

    def _critique_minor_issues(
        self,
        task_spec: Dict[str, Any],
        state: Dict[str, Any],
        draft: Any,
        artifacts: Dict[str, Any],
        verifier: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Critique minor issues.

        Args:
            task_spec: Task specification
            state: Current state
            draft: Draft output
            artifacts: Artifacts
            verifier: Verifier results

        Returns:
            Critique note
        """
        warnings = verifier.get("warnings", [])

        if warnings:
            return as_note(
                f"Minor warnings: {len(warnings)} issues",
                "address_warnings",
                0.5,
                ["warnings"],
                None
            )

        return as_note(
            "Nearly correct - minor polish needed",
            "final_polish",
            0.4,
            [],
            None
        )

    def record_critique(self, critique: Dict[str, Any], outcome: Dict[str, Any]):
        """Record critique and its outcome.

        Args:
            critique: The critique given
            outcome: Outcome after applying critique
        """
        self.critique_history.append({
            "critique": critique,
            "outcome": outcome,
            "improved": outcome.get("score", 0) > 0.5
        })

    def get_effectiveness(self) -> Dict[str, Any]:
        """Get critique effectiveness metrics.

        Returns:
            Effectiveness metrics
        """
        if not self.critique_history:
            return {
                "total_critiques": 0,
                "improvement_rate": 0.0
            }

        total = len(self.critique_history)
        improved = sum(1 for c in self.critique_history if c["improved"])

        return {
            "total_critiques": total,
            "improvement_rate": improved / total if total > 0 else 0.0
        }


class ReflexionLoop:
    """Reflexion loop with critic-driven refinement."""

    def __init__(
        self,
        critic: Critic,
        max_iterations: int = 3,
        min_score_threshold: float = 0.8
    ):
        """Initialize reflexion loop.

        Args:
            critic: Critic instance
            max_iterations: Maximum refinement iterations
            min_score_threshold: Minimum score to accept
        """
        self.critic = critic
        self.max_iterations = max_iterations
        self.min_score_threshold = min_score_threshold

    def refine(
        self,
        task_spec: Dict[str, Any],
        initial_draft: Any,
        executor_fn: Any,
        verifier_fn: Any
    ) -> Dict[str, Any]:
        """Refine draft using critic feedback.

        Args:
            task_spec: Task specification
            initial_draft: Initial draft
            executor_fn: Function to execute refinement
            verifier_fn: Function to verify output

        Returns:
            Refined result dict
        """
        draft = initial_draft
        state = {"iteration": 0, "critiques": []}

        for iteration in range(self.max_iterations):
            state["iteration"] = iteration

            # Verify current draft
            artifacts = {"draft": draft, "tools_used": []}
            verifier_result = verifier_fn(draft, task_spec)

            # Check if acceptable
            if verifier_result.get("pass", False) or verifier_result.get("score", 0) >= self.min_score_threshold:
                return {
                    "draft": draft,
                    "iterations": iteration + 1,
                    "final_score": verifier_result.get("score", 0),
                    "critiques": state["critiques"]
                }

            # Get critique
            critique = self.critic.review(task_spec, state, draft, artifacts, verifier_result)
            state["critiques"].append(critique)

            # If no suggested fix, can't improve
            if not critique.get("suggested_fix"):
                break

            # Apply refinement (simulated - in production would use actual executor)
            draft = self._apply_critique(draft, critique, task_spec)

        # Return best result even if not perfect
        final_verification = verifier_fn(draft, task_spec)
        return {
            "draft": draft,
            "iterations": self.max_iterations,
            "final_score": final_verification.get("score", 0),
            "critiques": state["critiques"],
            "max_iterations_reached": True
        }

    def _apply_critique(
        self,
        draft: Any,
        critique: Dict[str, Any],
        task_spec: Dict[str, Any]
    ) -> Any:
        """Apply critique to draft using real execution.

        Args:
            draft: Current draft
            critique: Critique to apply
            task_spec: Task specification

        Returns:
            Refined draft
        """
        suggested_fix = critique.get("suggested_fix", "")

        if not suggested_fix or suggested_fix in ["rethink_strategy", "refine_approach", "final_polish"]:
            # Generic fixes - just mark as refined
            if isinstance(draft, dict):
                refined = draft.copy()
                refined["refinement"] = suggested_fix
                refined["critique_applied"] = True
                return refined
            return draft

        # Try to use real executor for specific fixes
        try:
            from src.agentflow.executor import Executor
            from src.agentflow.types import TaskSpec

            executor = Executor()

            # Convert critique to executable decision
            decision = self._critique_to_decision(critique, task_spec, draft)

            # Execute refinement
            state = {"context": str(draft), "critique": critique}
            exec_result = executor.run(decision, state, kloros_instance=None)

            # Extract refined output
            if exec_result.get("success", False):
                refined_answer = exec_result.get("artifacts", {}).get("answer", draft)
                return refined_answer
            else:
                # Execution failed, return original with metadata
                if isinstance(draft, dict):
                    refined = draft.copy()
                    refined["refinement"] = suggested_fix
                    refined["critique_applied"] = True
                    refined["refinement_failed"] = True
                    return refined
                return draft

        except Exception as e:
            # Fallback to simulated refinement
            if isinstance(draft, dict):
                refined = draft.copy()
                refined["refinement"] = suggested_fix
                refined["critique_applied"] = True
                refined["error"] = str(e)
                return refined
            return draft

    def _critique_to_decision(
        self,
        critique: Dict[str, Any],
        task_spec: Dict[str, Any],
        draft: Any
    ) -> Dict[str, Any]:
        """Convert critique to executable decision.

        Args:
            critique: Critique dict
            task_spec: Task specification
            draft: Current draft

        Returns:
            Decision dict for executor
        """
        suggested_fix = critique.get("suggested_fix", "")

        # Map common fixes to tools
        fix_to_tool = {
            "prefer_code_exec": ("code_exec", {}),
            "use_code_tools": ("code_exec", {}),
            "validate_syntax": ("syntax_check", {"code": str(draft)}),
            "optimize_performance": ("optimize", {"target": str(draft)}),
            "address_warnings": ("lint", {"code": str(draft)})
        }

        if suggested_fix in fix_to_tool:
            tool, args = fix_to_tool[suggested_fix]
            return {
                "tool": tool,
                "args": args,
                "rationale": critique.get("diagnosis", ""),
                "confidence": critique.get("confidence", 0.5),
                "done": True
            }

        # Default: generic refinement
        return {
            "tool": "refine",
            "args": {"draft": str(draft), "fix": suggested_fix},
            "rationale": critique.get("diagnosis", ""),
            "confidence": critique.get("confidence", 0.5),
            "done": True
        }
