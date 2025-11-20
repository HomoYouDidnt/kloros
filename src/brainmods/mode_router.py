"""Cognitive mode router for task-appropriate processing."""
from typing import Dict, Any, Optional, List


class ModeRouter:
    """Routes tasks to appropriate cognitive modes based on complexity and risk."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize mode router.

        Args:
            config: Configuration dict
        """
        self.config = config or {}

        # Keywords indicating complex tasks
        self.hard_keywords = self.config.get("hard_keywords", [
            "prove", "optimize", "formal", "api design", "security",
            "theorem", "compiler", "plan", "architecture", "design",
            "complex", "difficult", "challenge"
        ])

        # Keywords indicating risky tasks
        self.risky_keywords = self.config.get("risky_keywords", [
            "delete", "remove", "drop", "modify", "change", "update",
            "production", "database", "system", "critical"
        ])

    def route(self, task_spec: Dict[str, Any]) -> str:
        """Route task to appropriate mode.

        Modes:
        - light: Simple queries, fast responses
        - standard: Normal complexity, balanced
        - thunderdome: Complex reasoning, maximum resources

        Args:
            task_spec: Task specification dict

        Returns:
            Mode name ('light', 'standard', or 'thunderdome')
        """
        # Extract query
        query = (
            task_spec.get("query") or
            task_spec.get("prompt") or
            task_spec.get("text") or
            ""
        ).lower()

        # Check for explicit mode request
        if "mode" in task_spec:
            return task_spec["mode"]

        # Check if task requires permissions (risky)
        requires_permissions = bool(task_spec.get("requires_permissions"))
        has_risk_tags = bool(set(task_spec.get("tags", [])) & {"risky", "dangerous", "critical"})

        if requires_permissions or has_risk_tags:
            return "standard"  # Use standard mode for safety

        # Check complexity
        is_hard = any(keyword in query for keyword in self.hard_keywords)

        if is_hard:
            return "thunderdome"

        # Check if query is very short/simple
        if len(query.split()) <= 5 and not any(char in query for char in ["?", "how", "why", "what"]):
            return "light"

        # Default to standard
        return "standard"

    def get_mode_config(self, mode: str) -> Dict[str, Any]:
        """Get configuration for a mode.

        Args:
            mode: Mode name

        Returns:
            Mode configuration dict
        """
        mode_configs = {
            "light": {
                "latency_ms": 2000,
                "tool_calls": 2,
                "tokens": 1200,
                "ace": True,
                "agentflow": True
            },
            "standard": {
                "latency_ms": 5000,
                "tool_calls": 4,
                "tokens": 3500,
                "ace": True,
                "agentflow": True
            },
            "thunderdome": {
                "latency_ms": 9000,
                "tool_calls": 7,
                "tokens": 6000,
                "ace": True,
                "agentflow": True,
                "d_ream_generations": 3
            }
        }

        return mode_configs.get(mode, mode_configs["standard"])


def route_task(task_spec: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> str:
    """Convenience function to route task.

    Args:
        task_spec: Task specification
        config: Optional router config

    Returns:
        Mode name
    """
    router = ModeRouter(config)
    return router.route(task_spec)


class AdaptiveRouter:
    """Router that adapts based on task outcomes."""

    def __init__(self):
        """Initialize adaptive router."""
        self.router = ModeRouter()
        self.history: List[Dict[str, Any]] = []

    def route(self, task_spec: Dict[str, Any]) -> str:
        """Route with learning from history.

        Args:
            task_spec: Task specification

        Returns:
            Mode name
        """
        base_mode = self.router.route(task_spec)

        # Check if we should upgrade/downgrade based on history
        similar_tasks = self._find_similar_tasks(task_spec)

        if similar_tasks:
            # If similar tasks failed in lower mode, upgrade
            failures_in_mode = [
                t for t in similar_tasks
                if t["mode"] == base_mode and not t.get("success", False)
            ]

            if len(failures_in_mode) >= 2:
                # Upgrade mode
                if base_mode == "light":
                    base_mode = "standard"
                elif base_mode == "standard":
                    base_mode = "thunderdome"

        return base_mode

    def record_outcome(
        self,
        task_spec: Dict[str, Any],
        mode: str,
        success: bool,
        metrics: Optional[Dict[str, Any]] = None
    ):
        """Record task outcome for learning.

        Args:
            task_spec: Task specification
            mode: Mode used
            success: Whether task succeeded
            metrics: Optional performance metrics
        """
        self.history.append({
            "task_spec": task_spec,
            "mode": mode,
            "success": success,
            "metrics": metrics or {}
        })

    def _find_similar_tasks(self, task_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find similar tasks in history.

        Args:
            task_spec: Task to match

        Returns:
            List of similar tasks
        """
        query = (task_spec.get("query") or "").lower()
        if not query:
            return []

        query_words = set(query.split())
        similar = []

        for task in self.history[-50:]:  # Check recent history
            hist_query = (task["task_spec"].get("query") or "").lower()
            hist_words = set(hist_query.split())

            # Simple similarity: word overlap
            if query_words and hist_words:
                overlap = len(query_words & hist_words) / len(query_words)
                if overlap > 0.5:
                    similar.append(task)

        return similar

    def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics.

        Returns:
            Statistics dict
        """
        if not self.history:
            return {"total_tasks": 0}

        mode_counts = {}
        mode_successes = {}

        for task in self.history:
            mode = task["mode"]
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
            if task["success"]:
                mode_successes[mode] = mode_successes.get(mode, 0) + 1

        mode_success_rates = {
            mode: mode_successes.get(mode, 0) / mode_counts[mode]
            for mode in mode_counts
        }

        return {
            "total_tasks": len(self.history),
            "mode_counts": mode_counts,
            "mode_success_rates": mode_success_rates
        }
