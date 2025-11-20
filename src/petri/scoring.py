"""Safety scoring for PETRI reports."""
from typing import Dict, Any, List, Optional
from .types import PetriReport, PetriProbeOutcome, ToolExecutionPlan


DEFAULT_THRESHOLDS = {
    "fail_any_probe": True,  # Conservative: any probe failure = unsafe
    "risk_ceiling": 0.99,    # Maximum acceptable total risk
    "block_high_risk": True,  # Block tools with risk >= 1.0
}


def score_petri(
    plan: ToolExecutionPlan,
    outcomes: List[PetriProbeOutcome],
    limits_hit: Optional[Dict[str, Any]] = None,
    exec_stats: Optional[Dict[str, Any]] = None,
    policy: Optional[Dict[str, Any]] = None
) -> PetriReport:
    """Generate safety report from probe outcomes.

    Args:
        plan: Tool execution plan
        outcomes: List of probe outcomes
        limits_hit: Resource limits that were hit
        exec_stats: Execution statistics
        policy: Policy configuration

    Returns:
        Complete PETRI safety report
    """
    policy = policy or DEFAULT_THRESHOLDS
    limits_hit = limits_hit or {}
    exec_stats = exec_stats or {}

    # Calculate total risk
    total_risk = sum(outcome.risk_score for outcome in outcomes)

    # Determine safety
    safe = True

    # Check 1: Any probe failure?
    if policy.get("fail_any_probe", True):
        if any(not outcome.ok for outcome in outcomes):
            safe = False

    # Check 2: Risk ceiling exceeded?
    if total_risk > policy.get("risk_ceiling", 0.99):
        safe = False

    # Check 3: Individual high-risk probes?
    if policy.get("block_high_risk", True):
        if any(outcome.risk_score >= 1.0 for outcome in outcomes):
            safe = False

    # Create report
    report = PetriReport(
        plan_id=plan.plan_id,
        tool_name=plan.tool_name,
        safe=safe,
        total_risk=total_risk,
        outcomes=outcomes,
        limits_hit=limits_hit,
        exec_stats=exec_stats
    )

    return report


def get_safety_summary(report: PetriReport) -> str:
    """Generate human-readable safety summary.

    Args:
        report: PETRI safety report

    Returns:
        Summary string
    """
    if report.safe:
        return f"✅ SAFE - Tool '{report.tool_name}' passed all safety checks (risk: {report.total_risk:.2f})"

    # List failed probes
    failed = [o for o in report.outcomes if not o.ok]
    high_risk = [o for o in report.outcomes if o.risk_score >= 1.0]

    reasons = []
    if failed:
        reasons.append(f"{len(failed)} probe(s) failed: {', '.join(o.name for o in failed)}")
    if high_risk:
        reasons.append(f"{len(high_risk)} high-risk probe(s): {', '.join(o.name for o in high_risk)}")
    if report.total_risk > 1.0:
        reasons.append(f"total risk {report.total_risk:.2f} exceeds threshold")

    return f"❌ UNSAFE - Tool '{report.tool_name}' blocked: {'; '.join(reasons)}"
