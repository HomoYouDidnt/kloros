"""Response filtering middleware for KLoROS.

Detects and executes tool calls instead of speaking them.
"""

import re
from typing import Optional, Any, Tuple


# Enrollment command patterns
ENROLLMENT_PATTERNS = [
    r"\benroll\s+me\b",
    r"\badd\s+my\s+voice\b",
    r"\bremember\s+my\s+voice\b",
    r"\blearn\s+my\s+voice\b",
    r"\bregister\s+me\b",
    r"\bregister\s+my\s+voice\b",
]


def detect_enrollment_command(text: str) -> bool:
    """Detect if text contains an enrollment command.

    Args:
        text: Input text to check

    Returns:
        True if enrollment command detected, False otherwise
    """
    normalized = text.strip().lower()
    for pattern in ENROLLMENT_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return True
    return False


def detect_tool_call(text: str) -> Optional[str]:
    """Detect if text contains a tool call pattern.

    Args:
        text: Response text to check

    Returns:
        Tool name if detected, None otherwise.
        If multiple tools requested (separated by 'and', 'or', commas), returns only the first.
    """
    # Search for TOOL: anywhere in text (case-insensitive)
    match = re.search(r'\bTOOL:\s*(\S+)', text, re.IGNORECASE)
    if match:
        tool_spec = match.group(1).strip()
        # Handle multiple tool requests: "tool1 and tool2" or "tool1, tool2"
        # Split by common separators and take the first valid tool name
        for separator in [' and ', ' or ', ',', '&']:
            if separator in tool_spec:
                parts = [p.strip() for p in tool_spec.split(separator)]
                # Return first non-empty part
                for part in parts:
                    if part:
                        print(f"[response_filter] Multi-tool request detected: '{tool_spec}' → using first: '{part}'")
                        return part
        return tool_spec
    return None


# Tool name aliases for common variations
TOOL_ALIASES = {
    "system_status": "system_diagnostic",
    "diagnostic": "system_diagnostic",
    "audio_diagnostic": "audio_status",
    "memory_diagnostic": "memory_status",
    "stt_diagnostic": "stt_status",
}


def execute_tool(tool_name: str, kloros_instance: Any) -> str:
    """Execute a tool and return its result.
    
    Args:
        tool_name: Name of tool to execute
        kloros_instance: KLoROS instance with tool registry
        
    Returns:
        Tool execution result or error message
    """
    if not hasattr(kloros_instance, 'tool_registry'):
        return f"Tool system unavailable: {tool_name}"
    
    # Try alias resolution if tool not found
    resolved_name = TOOL_ALIASES.get(tool_name, tool_name)
    
    tool = kloros_instance.tool_registry.get_tool(resolved_name)
    if not tool:
        # Try original name if alias didn't work
        if resolved_name != tool_name:
            tool = kloros_instance.tool_registry.get_tool(tool_name)
        
        if not tool:
            # Attempt tool synthesis for unknown tools
            synthesized_tool = _attempt_tool_synthesis(tool_name, kloros_instance)
            if synthesized_tool:
                # Register the synthesized tool and execute it
                kloros_instance.tool_registry.register(synthesized_tool)
                try:
                    result = synthesized_tool.execute(kloros_instance)
                    return result
                except Exception as e:
                    return f"Synthesized tool execution failed: {e}"

            return f"Unknown tool: {tool_name}"
    
    try:
        result = tool.execute(kloros_instance)
        return result
    except Exception as e:
        return f"Tool execution failed: {e}"


def filter_response(text: str, kloros_instance: Any = None, is_user_input: bool = False) -> Tuple[str, bool]:
    """Filter response text for tool calls and enrollment commands.
    
    Args:
        text: Raw response text from LLM/RAG (or user input if is_user_input=True)
        kloros_instance: KLoROS instance for tool execution
        is_user_input: True if text is user input (for enrollment detection)
        
    Returns:
        Tuple of (filtered_text, enrollment_triggered)
        enrollment_triggered: True if enrollment command was detected
    """
    if not text or not text.strip():
        return text, False
    
    # Check for enrollment command in user input
    if is_user_input and detect_enrollment_command(text):
        return text, True
    
    # Check for tool call pattern in LLM response
    tool_name = detect_tool_call(text)
    if tool_name and kloros_instance:
        # Execute tool and return result instead of announcement
        return execute_tool(tool_name, kloros_instance), False
    
    return text, False


def _attempt_tool_synthesis(tool_name: str, kloros_instance: Any) -> Optional[Any]:
    """
    Attempt to synthesize a missing tool with safeguards against redundancy.

    Args:
        tool_name: Name of the requested tool
        kloros_instance: KLoROS instance

    Returns:
        Synthesized IntrospectionTool if successful, None otherwise
    """
    try:
        # Import synthesis system
        from ..tool_synthesis import ToolSynthesizer

        # Check if tool synthesis is enabled
        if not getattr(kloros_instance, 'enable_tool_synthesis', True):
            return None

        # Safeguard 1: Check for similar existing tools
        existing_tools = kloros_instance.tool_registry.tools.keys()
        similar_tools = _find_similar_tools(tool_name, existing_tools)

        if similar_tools:
            # Log that similar tools exist
            if hasattr(kloros_instance, 'log_event'):
                kloros_instance.log_event("tool_synthesis_blocked",
                                        tool_name=tool_name,
                                        similar_tools=similar_tools,
                                        reason="redundancy_prevention")
            return None

        # Safeguard 2: Rate limiting - max 3 synthesis attempts per hour
        if not _check_synthesis_rate_limit(tool_name, kloros_instance):
            return None

        # Initialize synthesizer
        synthesizer = ToolSynthesizer(kloros_instance)

        # Capture the failed request
        if not synthesizer.capture_failed_tool_request(tool_name):
            return None

        # Attempt synthesis
        synthesized_tool = synthesizer.synthesize_tool(tool_name)

        if synthesized_tool:
            # Log successful synthesis
            if hasattr(kloros_instance, 'log_event'):
                kloros_instance.log_event("tool_synthesized",
                                        tool_name=tool_name,
                                        success=True)

        return synthesized_tool

    except Exception as e:
        # Log synthesis failure
        if hasattr(kloros_instance, 'log_event'):
            kloros_instance.log_event("tool_synthesis_error",
                                    tool_name=tool_name,
                                    error=str(e))
        return None


def _find_similar_tools(requested_tool: str, existing_tools: list) -> list:
    """
    Find existing tools that are similar to the requested tool.

    Args:
        requested_tool: Name of the requested tool
        existing_tools: List of existing tool names

    Returns:
        List of similar tool names
    """
    similar = []
    requested_lower = requested_tool.lower()

    # Extract key words from requested tool name
    requested_words = set(re.findall(r'\w+', requested_lower))

    for existing_tool in existing_tools:
        existing_lower = existing_tool.lower()
        existing_words = set(re.findall(r'\w+', existing_lower))

        # Check for exact match or high similarity
        if requested_lower == existing_lower:
            similar.append(existing_tool)
            continue

        # Check for significant word overlap (>= 60% of words match)
        if len(requested_words) > 0:
            overlap = len(requested_words.intersection(existing_words))
            similarity = overlap / len(requested_words)

            if similarity >= 0.6:
                similar.append(existing_tool)

        # Check for partial matches in specific patterns
        if any(word in existing_lower for word in requested_words if len(word) > 3):
            # Check if it's the same category of tool
            categories = ['audio', 'system', 'memory', 'user', 'enrollment', 'diagnostic']

            for category in categories:
                if category in requested_lower and category in existing_lower:
                    similar.append(existing_tool)
                    break

    return similar


def _check_synthesis_rate_limit(tool_name: str, kloros_instance: Any) -> bool:
    """
    Check if tool synthesis rate limit allows this request.

    Args:
        tool_name: Name of the tool being synthesized
        kloros_instance: KLoROS instance

    Returns:
        True if synthesis is allowed, False if rate limited
    """
    try:
        from datetime import datetime, timedelta
        import json
        import os

        # Rate limit: max 3 synthesis attempts per hour per tool
        rate_limit_file = "/home/kloros/.kloros/synthesis_rate_limit.json"

        # Load existing rate limit data
        rate_data = {}
        if os.path.exists(rate_limit_file):
            try:
                with open(rate_limit_file, 'r') as f:
                    rate_data = json.load(f)
            except:
                rate_data = {}

        current_time = datetime.now()
        hour_ago = current_time - timedelta(hours=1)

        # Clean old entries
        tool_attempts = rate_data.get(tool_name, [])
        recent_attempts = [
            attempt for attempt in tool_attempts
            if datetime.fromisoformat(attempt) > hour_ago
        ]

        # Check rate limit
        if len(recent_attempts) >= 3:
            return False

        # Add current attempt
        recent_attempts.append(current_time.isoformat())
        rate_data[tool_name] = recent_attempts

        # Save updated rate data
        os.makedirs(os.path.dirname(rate_limit_file), exist_ok=True)
        with open(rate_limit_file, 'w') as f:
            json.dump(rate_data, f)

        return True

    except Exception:
        # If rate limiting fails, allow synthesis
        return True

