"""Macro selection policy."""
from typing import Dict, Any, Optional, List
from .types import Macro, MacroLibrary, MacroSelection
from .expander import validate_macro_preconditions, estimate_macro_cost


class MacroPolicy:
    """Policy for selecting macros based on context and hints."""

    def __init__(self, library: MacroLibrary, config: Optional[Dict[str, Any]] = None):
        """Initialize macro policy.

        Args:
            library: Macro library to select from
            config: Policy configuration
        """
        self.library = library
        self.config = config or {}
        self.fallback_threshold = self.config.get("fallback_threshold", 0.55)

    def select(
        self,
        state: Dict[str, Any],
        task_spec: Dict[str, Any],
        hints: Optional[List[str]] = None
    ) -> MacroSelection:
        """Select best macro for current context.

        Args:
            state: Current state
            task_spec: Task specification
            hints: ACE hints (can suggest macros)

        Returns:
            MacroSelection with chosen macro or None
        """
        hints = hints or []
        context = {
            "domain": task_spec.get("domain", state.get("domain", "")),
            "query": task_spec.get("query", state.get("context", "")),
            "query_type": self._infer_query_type(task_spec, state),
            "intent": self._infer_intent(task_spec, state, hints)
        }

        # Score all macros
        candidates = []
        for macro in self.library.macros:
            score, reason = self._score_macro(macro, context, hints)
            if score > 0:
                candidates.append((macro, score, reason))

        # Sort by score (descending)
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Select best if above threshold
        if candidates and candidates[0][1] >= self.fallback_threshold:
            best_macro, confidence, reason = candidates[0]

            # Extract parameters from context
            params = self._extract_params(best_macro, context)

            return MacroSelection(
                macro_id=best_macro.id,
                macro=best_macro,
                params=params,
                confidence=confidence,
                reason=reason
            )

        # No suitable macro - fallback to primitive planning
        return MacroSelection(
            macro_id=None,
            macro=None,
            params={},
            confidence=0.0,
            reason="No suitable macro found; fallback to primitive planning"
        )

    def _score_macro(
        self,
        macro: Macro,
        context: Dict[str, Any],
        hints: List[str]
    ) -> tuple[float, str]:
        """Score how well a macro fits the current context.

        Args:
            macro: Macro to score
            context: Current context
            hints: ACE hints

        Returns:
            Tuple of (score, reason)
        """
        score = 0.0
        reasons = []

        # Check preconditions
        satisfied, precond_reason = validate_macro_preconditions(macro, context)
        if not satisfied:
            return 0.0, precond_reason

        # Base score for preconditions satisfied
        score += 0.5
        reasons.append("preconditions_met")

        # Boost for domain match
        if macro.domain == context.get("domain", ""):
            score += 0.2
            reasons.append("domain_match")

        # Boost for high success rate
        success_rate = macro.success_rate
        if success_rate > 0.7:
            score += 0.2 * success_rate
            reasons.append(f"high_success_rate={success_rate:.2f}")

        # Boost if mentioned in ACE hints
        macro_name_lower = macro.name.lower()
        for hint in hints:
            if macro_name_lower in hint.lower() or macro.id in hint:
                score += 0.15
                reasons.append("ace_hint_match")
                break

        # Penalty for low efficiency (high cost/success ratio)
        if macro.stats.get("uses", 0) > 5:
            avg_latency = macro.stats.get("avg_latency_ms", 0)
            if avg_latency > macro.budgets.get("latency_ms", 4000):
                score -= 0.1
                reasons.append("high_latency")

        return min(score, 1.0), "; ".join(reasons)

    def _infer_query_type(self, task_spec: Dict[str, Any], state: Dict[str, Any]) -> str:
        """Infer query type from task and state."""
        query = task_spec.get("query", state.get("context", "")).lower()

        if any(word in query for word in ["what", "where", "when", "who", "which"]):
            return "factual"
        elif any(word in query for word in ["search", "find", "look for", "show"]):
            return "search"
        elif any(word in query for word in ["how", "explain", "why"]):
            return "knowledge"
        else:
            return "general"

    def _infer_intent(
        self,
        task_spec: Dict[str, Any],
        state: Dict[str, Any],
        hints: List[str]
    ) -> str:
        """Infer user intent from context."""
        query = task_spec.get("query", state.get("context", "")).lower()

        if any(word in query for word in ["status", "check", "working", "error"]):
            return "status"
        elif any(word in query for word in ["diagnose", "debug", "problem", "issue"]):
            return "diagnosis"
        elif any(word in query for word in ["discover", "available", "list", "show all"]):
            return "discovery"
        elif any(word in query for word in ["search", "find"]):
            return "search"
        else:
            return "general"

    def _extract_params(self, macro: Macro, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameters for macro from context."""
        params = {}

        # Extract common parameters
        if "query" in context:
            params["query"] = context["query"]

        # Try to extract character name for voice macros
        query = context.get("query", "").lower()
        for word in query.split():
            if word.capitalize() in ["Glados", "Wheatley", "Cave", "Caroline"]:
                params["character"] = word.lower()
                break

        return params
