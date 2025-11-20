"""
Pre-execution validation system for tool requests.

Validates tool requests before execution to prevent errors and provide
better feedback when tools are unavailable or misconfigured.
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

try:
    from src.self_heal.adapters.validator import emit_low_context
except ImportError:
    emit_low_context = None


# Feature flag: when False, context match is advisory-only and never hard-rejects
ENABLE_CONTEXT_REJECTION = False


@dataclass
class ValidationResult:
    """Result of pre-execution validation."""
    is_valid: bool
    error_message: str = ""
    suggestions: List[str] = None
    confidence: float = 0.0

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


class PreExecutionValidator:
    """Validates tool execution requests before they run."""

    def __init__(self, tool_registry=None, semantic_matcher=None, heal_bus=None):
        """
        Initialize validator with tool registry.

        Args:
            tool_registry: IntrospectionToolRegistry instance
            semantic_matcher: Optional SemanticToolMatcher for better suggestions
            heal_bus: Optional HealBus for emitting validation events
        """
        self.tool_registry = tool_registry
        self.semantic_matcher = semantic_matcher
        self.validation_cache = {}
        self.heal_bus = heal_bus

    def validate_tool_request(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        kloros_instance=None,
        context: str = ""
    ) -> ValidationResult:
        """
        Comprehensive validation of tool execution request.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments to pass to the tool
            kloros_instance: KLoROS instance for method checking
            context: Original user query for better suggestions

        Returns:
            ValidationResult with is_valid flag and error details
        """
        # Step 1: Check if tool exists
        if not self._tool_exists(tool_name):
            return self._handle_missing_tool(tool_name, context)

        # Step 2: Validate tool parameters
        param_validation = self._validate_parameters(tool_name, tool_args)
        if not param_validation.is_valid:
            return param_validation

        # Step 3: Check kloros_instance requirements
        if kloros_instance:
            instance_validation = self._validate_instance_requirements(
                tool_name, kloros_instance
            )
            if not instance_validation.is_valid:
                return instance_validation

        # Step 4: Contextual validation (does this tool make sense for the query?)
        context_validation = self._validate_context_match(tool_name, context)
        if not context_validation.is_valid:
            return context_validation

        # Step 5: Check manifest preconditions (if available)
        precondition_validation = self._validate_preconditions(tool_name, kloros_instance)
        if not precondition_validation.is_valid:
            return precondition_validation

        return ValidationResult(is_valid=True, confidence=1.0)

    def _tool_exists(self, tool_name: str) -> bool:
        """Check if tool is registered."""
        if not self.tool_registry:
            return False
        return tool_name in self.tool_registry.tools

    def _handle_missing_tool(self, tool_name: str, context: str) -> ValidationResult:
        """Handle case where requested tool doesn't exist."""
        suggestions = []

        if self.tool_registry:
            # Find similar tool names
            all_tools = list(self.tool_registry.tools.keys())
            similar = self._find_similar_tools(tool_name, all_tools)

            if similar:
                suggestions.append(f"Did you mean: {', '.join(similar[:3])}?")

            # Suggest tools based on context
            if context:
                contextual_tools = self._suggest_tools_for_context(context, all_tools)
                if contextual_tools:
                    suggestions.append(f"For your query, consider: {', '.join(contextual_tools[:3])}")

        error_msg = f"Tool '{tool_name}' does not exist in registry"

        return ValidationResult(
            is_valid=False,
            error_message=error_msg,
            suggestions=suggestions,
            confidence=0.0
        )

    def _find_similar_tools(self, tool_name: str, all_tools: List[str]) -> List[str]:
        """Find tools with similar names using fuzzy matching."""
        similar = []
        tool_lower = tool_name.lower().replace('_', ' ').replace('-', ' ')

        for tool in all_tools:
            tool_words = set(tool.lower().replace('_', ' ').replace('-', ' ').split())
            query_words = set(tool_lower.split())

            # Check for word overlap
            overlap = len(tool_words & query_words)
            if overlap > 0:
                similar.append((tool, overlap))

        # Sort by overlap count
        similar.sort(key=lambda x: x[1], reverse=True)
        return [t[0] for t in similar[:5]]

    def _suggest_tools_for_context(self, context: str, all_tools: List[str]) -> List[str]:
        """Suggest appropriate tools based on query context."""
        suggestions = []
        context_lower = context.lower()

        # Keyword-based suggestions
        keyword_map = {
            'memory': ['memory_status', 'list_memories', 'search_memory'],
            'audio': ['count_voice_samples', 'audio_device_info', 'sample_rate_info'],
            'system': ['system_status', 'component_status', 'system_diagnostic'],
            'conversation': ['conversation_length', 'conversation_summary', 'recent_topics'],
            'user': ['list_users', 'current_user', 'user_enrollment_status'],
            'search': ['search_memory', 'list_memories', 'recent_topics'],
            'status': ['system_status', 'memory_status', 'component_status'],
            'diagnostic': ['system_diagnostic', 'component_status', 'memory_status'],
        }

        for keyword, tools in keyword_map.items():
            if keyword in context_lower:
                for tool in tools:
                    if tool in all_tools and tool not in suggestions:
                        suggestions.append(tool)
        # If semantic matcher available, use it for better suggestions
        if self.semantic_matcher:
            try:
                semantic_matches = self.semantic_matcher.find_matching_tools(context, top_k=5, threshold=0.4)
                for tool_name, similarity, _ in semantic_matches:
                    if tool_name in all_tools and tool_name not in suggestions:
                        suggestions.insert(0, tool_name)  # Prioritize semantic matches
            except Exception:
                pass  # Fallback to keyword-based only

        return suggestions[:5]


    def _validate_parameters(self, tool_name: str, tool_args: Dict[str, Any]) -> ValidationResult:
        """Validate tool parameters against expected signature."""
        if not self.tool_registry:
            return ValidationResult(is_valid=True)

        tool = self.tool_registry.tools.get(tool_name)
        if not tool:
            return ValidationResult(is_valid=True)  # Already checked existence

        # Check required parameters
        expected_params = tool.parameters if hasattr(tool, 'parameters') else []
        required_params = [p for p in expected_params if getattr(p, 'required', False)]

        missing_params = []
        for param in required_params:
            param_name = param.name if hasattr(param, 'name') else str(param)
            if param_name not in tool_args:
                missing_params.append(param_name)

        if missing_params:
            return ValidationResult(
                is_valid=False,
                error_message=f"Missing required parameters: {', '.join(missing_params)}",
                confidence=0.0
            )

        return ValidationResult(is_valid=True, confidence=1.0)

    def _validate_instance_requirements(
        self,
        tool_name: str,
        kloros_instance
    ) -> ValidationResult:
        """Validate that kloros_instance has required attributes for this tool."""
        # Get tool code if it's a synthesized tool
        try:
            from .storage import SynthesizedToolStorage
            storage = SynthesizedToolStorage()
            tool_data = storage.load_tool(tool_name)

            if tool_data:
                tool_code, metadata = tool_data
                missing_attrs = self._check_required_attributes(tool_code, kloros_instance)

                if missing_attrs:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"KLoROS instance missing required attributes: {', '.join(missing_attrs)}",
                        suggestions=[
                            "Tool may need method bridging",
                            "Check if memory system is enabled",
                            "Verify component initialization"
                        ],
                        confidence=0.3
                    )
        except Exception:
            pass  # Not a synthesized tool or can't load

        return ValidationResult(is_valid=True, confidence=1.0)

    def _check_required_attributes(self, tool_code: str, kloros_instance) -> List[str]:
        """Extract required attributes from tool code and check if they exist."""
        missing = []

        # Find kloros_instance.X patterns
        pattern = r'kloros_instance\.(\w+)'
        matches = re.finditer(pattern, tool_code)

        checked = set()
        for match in matches:
            attr = match.group(1)
            if attr not in checked:
                checked.add(attr)
                if not hasattr(kloros_instance, attr):
                    missing.append(attr)

        return missing

    def _validate_context_match(self, tool_name: str, context: str) -> ValidationResult:
        """
        Validate that the selected tool makes sense for the query context.

        Now advisory-only: validates against tool PURPOSE (description) rather than name.
        When ENABLE_CONTEXT_REJECTION is False, low confidence logs warning but never rejects.
        """
        if not context:
            return ValidationResult(is_valid=True, confidence=0.5)

        # Validate against tool PURPOSE (description) rather than tool name
        tool_obj = None
        if self.tool_registry and hasattr(self.tool_registry, "tools"):
            tool_obj = self.tool_registry.tools.get(tool_name)

        # Use tool description (the actual purpose) instead of the name
        purpose_text = (getattr(tool_obj, "description", None) or tool_name or "").strip()

        context_lower = context.lower()
        purpose_lower = purpose_text.lower().replace('_', ' ').replace('-', ' ')

        # Extract key terms from context and tool purpose
        context_keywords = self._extract_keywords(context_lower)
        tool_keywords = self._extract_keywords(purpose_lower)

        # Check for keyword overlap
        overlap = len(context_keywords & tool_keywords)
        total_context_keywords = len(context_keywords)

        if total_context_keywords > 0:
            confidence = overlap / total_context_keywords
        else:
            confidence = 0.5

        # Advisory mode when ENABLE_CONTEXT_REJECTION is False
        # Check for environment override (used by chaos testing)
        import os
        env_threshold = os.environ.get("KLR_VALIDATOR_THRESHOLD")
        if env_threshold is not None:
            try:
                threshold = float(env_threshold)
            except ValueError:
                threshold = 0.10 if ENABLE_CONTEXT_REJECTION else 0.0
        else:
            threshold = 0.10 if ENABLE_CONTEXT_REJECTION else 0.0

        # If confidence is very low, this might be the wrong tool
        if confidence < threshold and total_context_keywords > 2:
            # Emit heal event for self-healing
            if emit_low_context and self.heal_bus:
                emit_low_context(self.heal_bus, tool_name, confidence)

            suggestions = []
            if self.tool_registry:
                better_tools = self._suggest_tools_for_context(
                    context,
                    list(self.tool_registry.tools.keys())
                )
                if better_tools:
                    suggestions.append(f"Consider instead: {', '.join(better_tools[:3])}")

            # Return with proper field order: is_valid, error_message, suggestions, confidence
            return ValidationResult(
                is_valid=False,
                error_message=f"Tool '{tool_name}' doesn't match query context (conf={confidence:.2f}, advisory_only={not ENABLE_CONTEXT_REJECTION})",
                suggestions=suggestions,
                confidence=confidence
            )

        return ValidationResult(is_valid=True, confidence=max(confidence, 0.5))

    def _extract_keywords(self, text: str) -> set:
        """Extract meaningful keywords from text."""
        # Remove common stopwords
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might',
            'can', 'your', 'my', 'their', 'our', 'his', 'her', 'its', 'this', 'that',
            'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what',
            'which', 'who', 'when', 'where', 'why', 'how', 'please', 'yes', 'no'
        }

        words = re.findall(r'\b\w+\b', text.lower())
        keywords = {w for w in words if w not in stopwords and len(w) > 2}

        return keywords

    def get_validation_stats(self) -> Dict[str, Any]:
        """Get statistics about validation operations."""
        return {
            "cache_size": len(self.validation_cache),
            "tool_count": len(self.tool_registry.tools) if self.tool_registry else 0
        }

    def _validate_preconditions(self, tool_name: str, kloros_instance=None) -> ValidationResult:
        """
        Check manifest preconditions before tool execution.

        Args:
            tool_name: Name of the tool
            kloros_instance: KLoROS instance for state checking

        Returns:
            ValidationResult with precondition status
        """
        if not self.tool_registry or tool_name not in self.tool_registry.tools:
            return ValidationResult(is_valid=True)  # No tool obj, skip

        tool_obj = self.tool_registry.tools[tool_name]

        # Check if tool has manifest with planning.preconditions
        if not hasattr(tool_obj, 'manifest') or not isinstance(tool_obj.manifest, dict):
            return ValidationResult(is_valid=True)  # No manifest, skip

        planning = tool_obj.manifest.get('planning', {})
        preconditions = planning.get('preconditions', [])

        if not preconditions:
            return ValidationResult(is_valid=True)  # No preconditions defined

        # Simple precondition checking (can be extended)
        failed_conditions = []
        for condition in preconditions:
            # Example checks (extend as needed):
            # - "requires_network": check network availability
            # - "requires_gpu": check GPU availability
            # - "requires_memory": check memory state
            
            if "requires_" in condition.lower():
                # For now, log and allow (can be extended with actual checks)
                pass
            # Additional precondition logic can be added here

        if failed_conditions:
            return ValidationResult(
                is_valid=False,
                error_message=f"Preconditions not met: {', '.join(failed_conditions)}",
                suggestions=["Ensure required conditions are satisfied before using this tool"]
            )

        return ValidationResult(is_valid=True)

    def record_postconditions(self, tool_name: str, success: bool) -> None:
        """
        Record postconditions after tool execution (for observability).

        Args:
            tool_name: Name of the executed tool
            success: Whether execution succeeded
        """
        if not self.tool_registry or tool_name not in self.tool_registry.tools:
            return

        tool_obj = self.tool_registry.tools[tool_name]

        # Check if tool has manifest with planning.postconditions
        if not hasattr(tool_obj, 'manifest') or not isinstance(tool_obj.manifest, dict):
            return

        planning = tool_obj.manifest.get('planning', {})
        postconditions = planning.get('postconditions', [])

        if not postconditions:
            return

        # Log postconditions for observability
        try:
            from .logging import log
            log("tool.postconditions", tool=tool_name, success=success, 
                postconditions=postconditions)
        except ImportError:
            pass  # logging module not available

