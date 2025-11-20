"""PETRI runner - orchestrates safety checks."""
import os
import uuid
from typing import List, Callable, Optional, Dict, Any
from .types import ToolExecutionPlan, PetriReport
from .probes import DEFAULT_PROBES
from .scoring import score_petri, get_safety_summary
from .telemetry import log_report, log_incident
from .risk_classifier import assess_risk, should_run_petri


def check_tool_safety(
    tool_name: str,
    args: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None,
    probes: Optional[List[Callable]] = None,
    config: Optional[Dict[str, Any]] = None
) -> PetriReport:
    """Check safety of a tool execution before running it.

    Args:
        tool_name: Name of tool to execute
        args: Tool arguments
        context: Additional context
        probes: List of probe functions (default: DEFAULT_PROBES)
        config: PETRI configuration

    Returns:
        PETRI safety report
    """
    config = config or {}
    probes = probes or DEFAULT_PROBES
    context = context or {}

    # Create execution plan
    plan = ToolExecutionPlan(
        tool_name=tool_name,
        args=args,
        context=context,
        plan_id=str(uuid.uuid4())[:8]
    )

    # Assess risk
    plan = assess_risk(plan)

    # Check if PETRI is needed
    petri_threshold = config.get("risk_threshold", 0.3)
    if not should_run_petri(plan, threshold=petri_threshold):
        # Low risk - skip detailed probes
        return PetriReport(
            plan_id=plan.plan_id,
            tool_name=tool_name,
            safe=True,
            total_risk=plan.risk_score,
            outcomes=[],
            exec_stats={"skipped_probes": "low_risk"}
        )

    # Run safety probes
    env = {
        "scratch": os.environ.get("KLR_SANDBOX_TMP", "/tmp/petri_scratch"),
        "allow_network": os.environ.get("KLR_ALLOW_NETWORK", "0") == "1"
    }

    outcomes = []
    for probe in probes:
        try:
            outcome = probe(plan, env)
            outcomes.append(outcome)
        except Exception as e:
            # Probe failure = unsafe
            from .types import PetriProbeOutcome
            outcomes.append(PetriProbeOutcome(
                name=probe.__name__,
                ok=False,
                risk_score=1.0,
                notes=f"Probe exception: {e}"
            ))

    # Score and generate report
    policy = config.get("policy", {})
    report = score_petri(plan, outcomes, policy=policy)

    # Log report
    if config.get("telemetry_enabled", True):
        try:
            log_report(report)
        except Exception as e:
            print(f"[petri] Failed to log report: {e}")

    # Log incident if unsafe
    if not report.safe:
        try:
            log_incident(
                tool_name=tool_name,
                reason="Safety check failed",
                details={
                    "plan_id": plan.plan_id,
                    "risk_score": plan.risk_score,
                    "risk_tags": plan.risk_tags,
                    "total_risk": report.total_risk
                }
            )
        except Exception as e:
            print(f"[petri] Failed to log incident: {e}")

    return report


def enforce_safety(report: PetriReport, raise_on_unsafe: bool = True) -> bool:
    """Enforce safety decision from PETRI report.

    Args:
        report: PETRI safety report
        raise_on_unsafe: Whether to raise exception if unsafe

    Returns:
        True if safe, False otherwise

    Raises:
        RuntimeError: If unsafe and raise_on_unsafe=True
    """
    if not report.safe:
        summary = get_safety_summary(report)
        print(f"[petri] {summary}")

        if raise_on_unsafe:
            raise RuntimeError(
                f"PETRI safety check failed for '{report.tool_name}': "
                f"total_risk={report.total_risk:.2f}, "
                f"failed_probes={[o.name for o in report.outcomes if not o.ok]}"
            )
        return False

    return True


def quick_risk_check(tool_name: str, args: Dict[str, Any]) -> float:
    """Quick risk assessment without full PETRI probes.

    Args:
        tool_name: Tool name
        args: Tool arguments

    Returns:
        Risk score (0.0 = safe, higher = riskier)
    """
    plan = ToolExecutionPlan(
        tool_name=tool_name,
        args=args,
        plan_id="quick"
    )
    plan = assess_risk(plan)
    return plan.risk_score
