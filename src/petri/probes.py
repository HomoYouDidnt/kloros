"""Safety probes for tool execution validation."""
import os
from typing import Dict, Any, List, Callable
from .types import PetriProbeOutcome, ToolExecutionPlan


def ArgumentValidationProbe(plan: ToolExecutionPlan, env: Dict[str, Any]) -> PetriProbeOutcome:
    """Check for malicious argument patterns.

    Args:
        plan: Tool execution plan
        env: Execution environment

    Returns:
        Probe outcome
    """
    dangerous_patterns = [";", "&&", "||", "|", "`", "$", "../", "~/"]
    violations = []

    for arg_name, arg_value in plan.args.items():
        arg_str = str(arg_value)
        for pattern in dangerous_patterns:
            if pattern in arg_str:
                violations.append(f"{arg_name}:{pattern}")

    ok = len(violations) == 0
    risk_score = len(violations) * 0.5

    return PetriProbeOutcome(
        name="ArgumentValidationProbe",
        ok=ok,
        risk_score=risk_score,
        notes=f"Violations: {violations}" if violations else "All arguments valid"
    )


def FilesystemPolicyProbe(plan: ToolExecutionPlan, env: Dict[str, Any]) -> PetriProbeOutcome:
    """Check filesystem access is within allowed boundaries.

    Args:
        plan: Tool execution plan
        env: Execution environment

    Returns:
        Probe outcome
    """
    scratch_dir = env.get("scratch", "/tmp")
    forbidden_paths = ["/etc/", "/sys/", "/proc/", "/root/"]

    violations = []
    for arg_name in ["path", "file", "directory"]:
        if arg_name in plan.args:
            path_str = str(plan.args[arg_name])
            # Check for path escapes
            if any(forbidden in path_str for forbidden in forbidden_paths):
                violations.append(f"{arg_name} accesses forbidden path: {path_str}")

    ok = len(violations) == 0
    risk_score = 1.0 if not ok else 0.0

    return PetriProbeOutcome(
        name="FilesystemPolicyProbe",
        ok=ok,
        risk_score=risk_score,
        notes="; ".join(violations) if violations else "Filesystem access within policy"
    )


def NetworkPolicyProbe(plan: ToolExecutionPlan, env: Dict[str, Any]) -> PetriProbeOutcome:
    """Check network access permissions.

    Args:
        plan: Tool execution plan
        env: Execution environment

    Returns:
        Probe outcome
    """
    allow_network = os.environ.get("KLR_ALLOW_NETWORK", "0") == "1"

    # Check if tool attempts network access
    has_network_args = any(
        key in plan.args for key in ["url", "endpoint", "host", "ip"]
    )
    has_http_in_args = "http" in str(plan.args).lower()

    attempts_network = has_network_args or has_http_in_args

    ok = allow_network or not attempts_network
    risk_score = 1.0 if not ok else 0.0

    notes = "Network access allowed" if allow_network else (
        "Network access blocked" if attempts_network else "No network access attempted"
    )

    return PetriProbeOutcome(
        name="NetworkPolicyProbe",
        ok=ok,
        risk_score=risk_score,
        notes=notes
    )


def ToolAllowlistProbe(plan: ToolExecutionPlan, env: Dict[str, Any]) -> PetriProbeOutcome:
    """Check if tool is in safe allowlist.

    Args:
        plan: Tool execution plan
        env: Execution environment

    Returns:
        Probe outcome
    """
    from .risk_classifier import SAFE_TOOLS, HIGH_RISK_TOOLS

    tool_name = plan.tool_name.lower()

    if tool_name in HIGH_RISK_TOOLS:
        return PetriProbeOutcome(
            name="ToolAllowlistProbe",
            ok=False,
            risk_score=1.0,
            notes=f"Tool '{tool_name}' is on high-risk denylist"
        )

    if tool_name in SAFE_TOOLS:
        return PetriProbeOutcome(
            name="ToolAllowlistProbe",
            ok=True,
            risk_score=0.0,
            notes=f"Tool '{tool_name}' is on safe allowlist"
        )

    # Unknown tool - moderate risk
    return PetriProbeOutcome(
        name="ToolAllowlistProbe",
        ok=True,  # Allow but flag
        risk_score=0.3,
        notes=f"Tool '{tool_name}' is not in allowlist (unknown)"
    )


def CommandInjectionProbe(plan: ToolExecutionPlan, env: Dict[str, Any]) -> PetriProbeOutcome:
    """Detect potential command injection attempts.

    Args:
        plan: Tool execution plan
        env: Execution environment

    Returns:
        Probe outcome
    """
    injection_patterns = {
        "shell_operators": [";", "&&", "||", "|"],
        "command_substitution": ["`", "$(", "${"],
        "redirects": [">", ">>", "<"],
    }

    violations = []
    for arg_name, arg_value in plan.args.items():
        arg_str = str(arg_value)
        for pattern_type, patterns in injection_patterns.items():
            for pattern in patterns:
                if pattern in arg_str:
                    violations.append(f"{pattern_type} in {arg_name}")

    ok = len(violations) == 0
    risk_score = min(len(violations) * 0.8, 2.0)

    return PetriProbeOutcome(
        name="CommandInjectionProbe",
        ok=ok,
        risk_score=risk_score,
        notes="; ".join(violations) if violations else "No injection patterns detected"
    )


def ResourceLimitProbe(plan: ToolExecutionPlan, env: Dict[str, Any]) -> PetriProbeOutcome:
    """Check if execution would exceed resource limits.

    Args:
        plan: Tool execution plan
        env: Execution environment

    Returns:
        Probe outcome
    """
    # Check for obviously expensive operations
    expensive_patterns = ["recursive", "all", "*", "**", "everything"]

    flags = []
    for arg_value in plan.args.values():
        arg_str = str(arg_value).lower()
        for pattern in expensive_patterns:
            if pattern in arg_str:
                flags.append(pattern)

    risk_score = len(flags) * 0.2

    return PetriProbeOutcome(
        name="ResourceLimitProbe",
        ok=risk_score < 0.5,
        risk_score=risk_score,
        notes=f"Expensive patterns: {flags}" if flags else "Resource usage appears reasonable"
    )


# Default probe suite
DEFAULT_PROBES: List[Callable] = [
    ArgumentValidationProbe,
    FilesystemPolicyProbe,
    NetworkPolicyProbe,
    ToolAllowlistProbe,
    CommandInjectionProbe,
    ResourceLimitProbe,
]
