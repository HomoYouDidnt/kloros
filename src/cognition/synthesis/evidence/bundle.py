"""
Evidence Bundle Generation

Creates comprehensive audit trail for tool promotion decisions including:
- Shadow test results and statistics
- Performance metrics vs baseline
- Safety validation results
- Promotion decision record
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from pathlib import Path
from datetime import datetime
import json


@dataclass
class ShadowTestResult:
    """Individual shadow test outcome."""
    timestamp: str
    baseline_reward: float
    candidate_reward: float
    delta: float
    latency_ms: float
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """Performance statistics vs baseline."""
    trials: int
    wins: int
    losses: int
    ties: int
    win_rate: float
    avg_delta: float
    median_delta: float
    p95_latency_ms: float
    p99_latency_ms: float
    total_invocations: int


@dataclass
class SafetyValidation:
    """Safety check results."""
    passed: bool
    checks_run: List[str]
    violations: List[str]
    allowlist_ok: bool
    forbidden_patterns_ok: bool
    resource_limits_ok: bool
    timestamp: str


@dataclass
class PromotionDecision:
    """Final promotion decision record."""
    promoted: bool
    decision_timestamp: str
    decision_reason: str
    gates_passed: List[str]
    gates_failed: List[str]
    approver: str  # "automatic" or username
    override_reason: Optional[str] = None


@dataclass
class EvidenceBundle:
    """Complete evidence bundle for a tool promotion."""
    tool_name: str
    version: str
    created_at: str

    # Shadow testing
    shadow_results: List[ShadowTestResult] = field(default_factory=list)
    performance: Optional[PerformanceMetrics] = None

    # Safety
    safety: Optional[SafetyValidation] = None

    # Decision
    decision: Optional[PromotionDecision] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EvidenceBundle':
        """Load from dictionary."""
        # Convert nested structures
        shadow_results = [
            ShadowTestResult(**r) for r in data.get('shadow_results', [])
        ]

        perf_data = data.get('performance')
        performance = PerformanceMetrics(**perf_data) if perf_data else None

        safety_data = data.get('safety')
        safety = SafetyValidation(**safety_data) if safety_data else None

        decision_data = data.get('decision')
        decision = PromotionDecision(**decision_data) if decision_data else None

        return cls(
            tool_name=data['tool_name'],
            version=data['version'],
            created_at=data['created_at'],
            shadow_results=shadow_results,
            performance=performance,
            safety=safety,
            decision=decision,
            metadata=data.get('metadata', {})
        )


def generate_bundle(
    tool_name: str,
    version: str,
    shadow_outcomes: List[Dict[str, Any]],
    stats: Dict[str, Any],
    safety_checks: Dict[str, Any],
    decision: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None
) -> EvidenceBundle:
    """
    Generate evidence bundle from promotion data.

    Args:
        tool_name: Name of the tool
        version: Tool version
        shadow_outcomes: List of shadow test results
        stats: Performance statistics
        safety_checks: Safety validation results
        decision: Promotion decision record
        metadata: Additional metadata

    Returns:
        Complete evidence bundle
    """
    # Convert shadow outcomes
    shadow_results = []
    for outcome in shadow_outcomes:
        shadow_results.append(ShadowTestResult(
            timestamp=outcome.get('timestamp', datetime.now().isoformat()),
            baseline_reward=outcome.get('baseline_reward', 0.0),
            candidate_reward=outcome.get('candidate_reward', 0.0),
            delta=outcome.get('delta', 0.0),
            latency_ms=outcome.get('latency_ms', 0.0),
            context=outcome.get('context', {})
        ))

    # Build performance metrics
    performance = PerformanceMetrics(
        trials=stats.get('trials', 0),
        wins=stats.get('wins', 0),
        losses=stats.get('losses', 0),
        ties=stats.get('ties', 0),
        win_rate=stats.get('win_rate', 0.0),
        avg_delta=stats.get('avg_delta', 0.0),
        median_delta=stats.get('median_delta', 0.0),
        p95_latency_ms=stats.get('p95_latency_ms', 0.0),
        p99_latency_ms=stats.get('p99_latency_ms', 0.0),
        total_invocations=stats.get('total_invocations', 0)
    )

    # Build safety validation
    safety = SafetyValidation(
        passed=safety_checks.get('passed', False),
        checks_run=safety_checks.get('checks_run', []),
        violations=safety_checks.get('violations', []),
        allowlist_ok=safety_checks.get('allowlist_ok', False),
        forbidden_patterns_ok=safety_checks.get('forbidden_patterns_ok', False),
        resource_limits_ok=safety_checks.get('resource_limits_ok', True),
        timestamp=safety_checks.get('timestamp', datetime.now().isoformat())
    )

    # Build promotion decision
    prom_decision = PromotionDecision(
        promoted=decision.get('promoted', False),
        decision_timestamp=decision.get('timestamp', datetime.now().isoformat()),
        decision_reason=decision.get('reason', 'unknown'),
        gates_passed=decision.get('gates_passed', []),
        gates_failed=decision.get('gates_failed', []),
        approver=decision.get('approver', 'automatic'),
        override_reason=decision.get('override_reason')
    )

    return EvidenceBundle(
        tool_name=tool_name,
        version=version,
        created_at=datetime.now().isoformat(),
        shadow_results=shadow_results,
        performance=performance,
        safety=safety,
        decision=prom_decision,
        metadata=metadata or {}
    )


def save_bundle(bundle: EvidenceBundle, base_dir: str = "/home/kloros/.kloros/synth/evidence") -> Path:
    """
    Save evidence bundle to disk.

    Args:
        bundle: Evidence bundle to save
        base_dir: Base directory for evidence storage

    Returns:
        Path to saved bundle
    """
    base_path = Path(base_dir)
    tool_dir = base_path / bundle.tool_name / bundle.version
    tool_dir.mkdir(parents=True, exist_ok=True)

    # Save main bundle
    bundle_path = tool_dir / "bundle.json"
    bundle_path.write_text(bundle.to_json())

    # Save shadow results separately for analysis
    shadow_path = tool_dir / "shadow_results.jsonl"
    with shadow_path.open('w') as f:
        for result in bundle.shadow_results:
            f.write(json.dumps(asdict(result)) + '\n')

    # Save summary
    summary = {
        "tool": bundle.tool_name,
        "version": bundle.version,
        "created": bundle.created_at,
        "promoted": bundle.decision.promoted if bundle.decision else False,
        "trials": bundle.performance.trials if bundle.performance else 0,
        "win_rate": bundle.performance.win_rate if bundle.performance else 0.0,
        "safety_passed": bundle.safety.passed if bundle.safety else False
    }

    summary_path = tool_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    return bundle_path


def load_bundle(tool_name: str, version: str, base_dir: str = "/home/kloros/.kloros/synth/evidence") -> Optional[EvidenceBundle]:
    """
    Load evidence bundle from disk.

    Args:
        tool_name: Name of the tool
        version: Tool version
        base_dir: Base directory for evidence storage

    Returns:
        Evidence bundle or None if not found
    """
    bundle_path = Path(base_dir) / tool_name / version / "bundle.json"

    if not bundle_path.exists():
        return None

    data = json.loads(bundle_path.read_text())
    return EvidenceBundle.from_dict(data)


def list_bundles(base_dir: str = "/home/kloros/.kloros/synth/evidence") -> List[Dict[str, str]]:
    """
    List all evidence bundles.

    Returns:
        List of {tool, version, path} dicts
    """
    base_path = Path(base_dir)
    bundles = []

    if not base_path.exists():
        return bundles

    for tool_dir in base_path.iterdir():
        if not tool_dir.is_dir():
            continue

        for version_dir in tool_dir.iterdir():
            if not version_dir.is_dir():
                continue

            bundle_path = version_dir / "bundle.json"
            if bundle_path.exists():
                bundles.append({
                    "tool": tool_dir.name,
                    "version": version_dir.name,
                    "path": str(bundle_path)
                })

    return bundles
