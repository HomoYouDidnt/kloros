"""Risk classification for tool executions."""
from typing import List, Dict, Any
from .types import ToolExecutionPlan


# Risk allowlists and denylist patterns
SAFE_TOOLS = {
    # Read-only or low-risk tools
    "rag_query", "search_voice_samples", "list_audio_sources",
    "get_microphone_info", "get_speaker_info", "explain_reasoning",
    "check_recent_errors", "search_tools", "show_voices"
}

HIGH_RISK_TOOLS = {
    # System modification or external I/O
    "execute_shell", "run_command", "install_package",
    "modify_config", "restart_service", "write_file"
}

RISKY_ARGS = {
    # Argument patterns that indicate risk
    "system", "shell", "exec", "sudo", "rm", "delete",
    "http://", "https://", "ftp://", "../", "~/"
}


def assess_risk(plan: ToolExecutionPlan) -> ToolExecutionPlan:
    """Assess risk level of a tool execution plan.

    Args:
        plan: Tool execution plan to assess

    Returns:
        Updated plan with risk_score and risk_tags populated
    """
    risk_score = 0.0
    risk_tags = []

    tool_name = plan.tool_name.lower()

    # Check 1: Known high-risk tools
    if tool_name in HIGH_RISK_TOOLS:
        risk_score += 1.0
        risk_tags.append("high_risk_tool")

    # Check 2: Known safe tools get a pass
    if tool_name in SAFE_TOOLS:
        plan.risk_score = 0.0
        plan.risk_tags = []
        return plan

    # Check 3: New/unknown tools are risky
    if tool_name not in SAFE_TOOLS and tool_name not in HIGH_RISK_TOOLS:
        risk_score += 0.3
        risk_tags.append("unknown_tool")

    # Check 4: Risky argument patterns
    for arg_name, arg_value in plan.args.items():
        arg_str = str(arg_value).lower()
        for risky_pattern in RISKY_ARGS:
            if risky_pattern in arg_str:
                risk_score += 0.5
                risk_tags.append(f"risky_arg:{arg_name}")
                break

    # Check 5: External network access
    if "url" in plan.args or "http" in str(plan.args).lower():
        risk_score += 0.4
        risk_tags.append("external_network")

    # Check 6: File system access
    if "path" in plan.args or "file" in plan.args:
        path_str = str(plan.args.get("path", plan.args.get("file", ""))).lower()
        if any(pattern in path_str for pattern in ["../", "~/", "/etc/", "/sys/"]):
            risk_score += 0.6
            risk_tags.append("filesystem_escape")

    # Check 7: Command injection patterns
    if any(arg for arg in plan.args.values() if isinstance(arg, str) and any(
        cmd in arg for cmd in [";", "&&", "||", "|", "`", "$"]
    )):
        risk_score += 0.8
        risk_tags.append("command_injection")

    plan.risk_score = min(risk_score, 2.0)  # Cap at 2.0
    plan.risk_tags = list(set(risk_tags))  # Deduplicate

    return plan


def should_run_petri(plan: ToolExecutionPlan, threshold: float = 0.3) -> bool:
    """Determine if PETRI sandbox check is needed.

    Args:
        plan: Tool execution plan
        threshold: Risk score threshold (default 0.3)

    Returns:
        True if PETRI check should be run
    """
    if not plan.risk_score:
        assess_risk(plan)

    return plan.risk_score >= threshold


def get_risk_summary(plan: ToolExecutionPlan) -> str:
    """Get human-readable risk summary.

    Args:
        plan: Tool execution plan

    Returns:
        Risk summary string
    """
    if not plan.risk_score:
        assess_risk(plan)

    if plan.risk_score == 0.0:
        return "✅ Low risk - safe to execute"
    elif plan.risk_score < 0.5:
        return f"⚠️ Low-medium risk ({plan.risk_score:.2f}): {', '.join(plan.risk_tags)}"
    elif plan.risk_score < 1.0:
        return f"⚠️ Medium risk ({plan.risk_score:.2f}): {', '.join(plan.risk_tags)}"
    else:
        return f"❌ High risk ({plan.risk_score:.2f}): {', '.join(plan.risk_tags)}"
