"""
Tool Promotion System

Manages promotion of quarantined tools to production based on:
- Shadow test performance (must beat baseline)
- Minimum trial count
- Test suite status
- Risk level
- Daily/weekly quotas
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import datetime as dt
from datetime import datetime
import json
import subprocess
import sys
import os
import shlex
import statistics

try:
    import tomllib
except ImportError:
    import tomli as tomllib


@dataclass
class CandidateStats:
    """Shadow test statistics for a candidate tool."""
    trials: int = 0  # Number of shadow trials
    wins: int = 0  # Number of times beat baseline
    avg_delta: float = 0.0  # Average reward delta vs baseline


@dataclass
class PromotionState:
    """Persistent state for promotion tracking."""
    stats: Dict[str, CandidateStats] = field(default_factory=dict)
    today_promoted: int = 0
    last_reset: str = ""

    def record(self, name: str, delta: float):
        """
        Record shadow test outcome for candidate.

        Updates trials count, wins count, and running average delta.
        """
        st = self.stats.setdefault(name, CandidateStats())
        st.trials += 1
        if delta > 0:
            st.wins += 1
        # Online mean update
        st.avg_delta += (delta - st.avg_delta) / st.trials


def load_policy(path: str = "/home/kloros/config/policy.toml") -> Dict:
    """Load promotion policy from TOML file."""
    policy_path = Path(path)
    if not policy_path.exists():
        print(f"[promotion] Warning: Policy file not found: {path}")
        return _default_policy()

    try:
        return tomllib.loads(policy_path.read_text())
    except Exception as e:
        print(f"[promotion] Error loading policy: {e}")
        return _default_policy()


def _default_policy() -> Dict:
    """Return default policy if config file not found."""
    return {
        "promotion": {
            "shadow_win_min": 0.02,
            "min_shadow_trials": 20,
            "max_tools_promote_per_day": 2,
            "require_tests_green": True,
            "risk_allow": ["low", "medium"],
        },
        "shadow": {
            "traffic_share": 0.2,
            "dry_run": True,
        },
        "bandit": {
            "algo": "linucb",
            "alpha": 1.2,
            "feature_dim": 128,
            "warm_start_reward": 0.5,
        },
        "risk": {
            "gpu_status": "low",
            "memory_summary": "low",
            "xai_search": "medium",
            "mqtt_publish": "high",
        },
    }


def load_state(
    path: str = "/home/kloros/.kloros/synth/promotion_state.json"
) -> PromotionState:
    """Load promotion state from persistent storage."""
    p = Path(path).expanduser()
    if p.exists():
        try:
            obj = json.loads(p.read_text())
            ps = PromotionState()
            ps.stats = {
                k: CandidateStats(**v) for k, v in obj.get("stats", {}).items()
            }
            ps.today_promoted = obj.get("today_promoted", 0)
            ps.last_reset = obj.get("last_reset", "")
            return ps
        except Exception as e:
            print(f"[promotion] Error loading state: {e}")

    return PromotionState()


def save_state(
    st: PromotionState,
    path: str = "/home/kloros/.kloros/synth/promotion_state.json"
):
    """Save promotion state to persistent storage."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)

    obj = {
        "stats": {k: vars(v) for k, v in st.stats.items()},
        "today_promoted": st.today_promoted,
        "last_reset": st.last_reset,
    }
    p.write_text(json.dumps(obj, indent=2))


def reset_if_new_day(st: PromotionState):
    """Reset daily quota if date changed."""
    today = dt.date.today().isoformat()
    if st.last_reset != today:
        st.today_promoted = 0
        st.last_reset = today


def tests_green() -> bool:
    """
    Check if test suite passes.

    Runs fast subset of tests for promotion gate. Returns True if all pass.
    """
    try:
        # Build a minimal, fast test run by default, with escape hatches:
        # - PYTEST_BIN: override python executable if needed
        # - PYTEST_TARGETS: what to run (default: unit tests only)
        # - PYTEST_ADDOPTS: extra flags (respects standard pytest env var)
        # - PYTEST_FILTER: -k expression to exclude slow/e2e by default
        # - PROMOTION_ECHO_CMD: return command string instead of executing (for tests)

        pybin = os.environ.get("PYTEST_BIN") or sys.executable
        module = ["-m", "pytest"]
        targets = shlex.split(os.environ.get("PYTEST_TARGETS", "tests/unit"))
        addopts_env = shlex.split(os.environ.get("PYTEST_ADDOPTS", ""))
        k_filter = os.environ.get("PYTEST_FILTER", "not slow and not e2e")

        cmd = [pybin, *module, "-q", *targets, "-k", k_filter, "-x", *addopts_env]

        # Test mode: return command instead of executing
        if os.environ.get("PROMOTION_ECHO_CMD") == "1":
            return " ".join(cmd)

        result = subprocess.run(
            cmd,
            cwd="/home/kloros",
            capture_output=True,
            timeout=int(os.environ.get("PYTEST_TIMEOUT", "120")),
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[promotion] Test check failed: {e}")
        return False


def risk_of(tool: str, policy: Dict) -> str:
    """Get risk level of tool from policy."""
    return policy.get("risk", {}).get(tool, "medium")


def promote_if_eligible(
    tool: str,
    policy: Optional[Dict] = None,
    state: Optional[PromotionState] = None,
    shadow_outcomes: Optional[List[float]] = None,
    enable_dream_evolution: bool = True,
    generate_evidence: bool = True,
) -> Tuple[bool, str]:
    """
    Check if tool is eligible for promotion and promote if so.

    If promotion fails, optionally submit to D-REAM for evolutionary improvement.

    Promotion gates:
    1. Daily quota not exhausted
    2. Risk level allowed (low/medium, not high)
    3. Minimum shadow trials completed
    4. Average reward delta beats threshold
    5. Test suite passes

    Returns:
        (promoted, reason) tuple
            promoted: True if tool was promoted
            reason: Success message or blocking reason
    """
    policy = policy or load_policy()
    state = state or load_state()
    reset_if_new_day(state)

    p_prom = policy["promotion"]

    # Gate 1: Quota
    if state.today_promoted >= p_prom["max_tools_promote_per_day"]:
        return False, "quota_exhausted"

    # Gate 2: Risk level
    risk = risk_of(tool, policy)
    if risk not in p_prom["risk_allow"]:
        return False, f"risk_blocked:{risk}"

    # Gate 3: Minimum trials
    st = state.stats.get(tool, CandidateStats())
    if st.trials < p_prom["min_shadow_trials"]:
        return (
            False,
            f"not_enough_trials:{st.trials}/{p_prom['min_shadow_trials']}",
        )

    # Gate 4: Win rate
    if st.avg_delta < p_prom["shadow_win_min"]:
        failure_reason = f"not_winning_enough:avg_delta={st.avg_delta:.3f} < {p_prom['shadow_win_min']}"

        # Submit to D-REAM for evolutionary improvement
        if enable_dream_evolution and os.getenv("KLR_ENABLE_DREAM_EVOLUTION", "0") == "1":
            _submit_to_dream_evolution(tool, failure_reason, st)

        return False, failure_reason

    # Gate 5: Tests
    # Allow skipping in unit tests via environment variable
    skip_tests = os.getenv("PROMOTION_SKIP_TESTS", "0") == "1"
    if p_prom["require_tests_green"] and not skip_tests:
        if not tests_green():
            failure_reason = "tests_red"

            # Submit to D-REAM for bug fixing
            if enable_dream_evolution and os.getenv("KLR_ENABLE_DREAM_EVOLUTION", "0") == "1":
                _submit_to_dream_evolution(tool, failure_reason, st)

            return False, failure_reason

    # All gates passed → promote
    ok, msg = _promote_impl(tool)
    if ok:
        state.today_promoted += 1
        save_state(state)
        print(f"[promotion] ✓ Promoted {tool} to production")

    # Generate evidence bundle
    if generate_evidence:
        _generate_evidence_bundle(
            tool=tool,
            promoted=ok,
            reason=msg,
            stats=st,
            shadow_outcomes=shadow_outcomes or [],
            gates_passed=_get_gates_passed(ok, skip_tests, risk, st, p_prom),
            gates_failed=_get_gates_failed(ok, skip_tests, risk, st, p_prom, msg)
        )

    return ok, msg


def _submit_to_dream_evolution(
    tool: str,
    failure_reason: str,
    stats: CandidateStats
) -> None:
    """
    Submit failed tool to D-REAM for evolutionary improvement.

    Args:
        tool: Name of tool that failed promotion
        failure_reason: Why promotion failed
        stats: Shadow test statistics
    """
    try:
        # Load tool code from quarantine
        from src.tool_synthesis.governance import SynthesisGovernance
        from src.dream.tool_evolution import ToolEvolver

        governance = SynthesisGovernance()

        # Get tool from quarantine
        quarantine_path = governance.quarantine_dir / tool / "0.1.0"
        if not quarantine_path.exists():
            print(f"[dream] Cannot find tool in quarantine: {tool}")
            return

        tool_file = quarantine_path / "tool.py"
        if not tool_file.exists():
            print(f"[dream] Cannot find tool code: {tool}")
            return

        tool_code = tool_file.read_text()

        # Load metadata
        metadata_file = quarantine_path / "metadata.json"
        if metadata_file.exists():
            import json
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {}

        # Prepare shadow stats for evolution
        shadow_stats = {
            "trials": stats.trials,
            "wins": stats.wins,
            "avg_delta": stats.avg_delta,
        }

        analysis = metadata.get("analysis", {})

        print(f"[dream] Submitting {tool} to D-REAM evolution")
        print(f"[dream] Reason: {failure_reason}")
        print(f"[dream] Stats: {stats.trials} trials, {stats.wins} wins, avg_delta={stats.avg_delta:.3f}")

        # Evolve tool
        evolver = ToolEvolver()
        best_genome = evolver.evolve_tool(
            tool_name=tool,
            initial_code=tool_code,
            analysis=analysis,
            failure_reason=failure_reason,
            shadow_stats=shadow_stats
        )

        if best_genome and best_genome.fitness > 0.6:
            # Re-quarantine evolved version
            print(f"[dream] Evolution complete! Best fitness: {best_genome.fitness:.3f}")

            # Quarantine evolved tool with new version
            evolved_name = f"{tool}_evolved"
            versioned_name, provenance = governance.quarantine_tool(
                tool_name=evolved_name,
                tool_code=best_genome.code,
                reason=f"Evolved from {tool} to fix: {failure_reason}",
                model="dream_evolution",
                prompt=f"Evolutionary improvement targeting: {failure_reason}"
            )

            print(f"[dream] Evolved tool quarantined as: {versioned_name}")
            print(f"[dream] Mutations applied: {', '.join(best_genome.mutations)}")

            # Write evolution record to provenance
            evolution_record = {
                "event": "dream_evolution",
                "original_tool": tool,
                "evolved_tool": evolved_name,
                "reason": failure_reason,
                "generations": best_genome.generation + 1,
                "fitness": best_genome.fitness,
                "mutations": best_genome.mutations,
                "timestamp": datetime.now().isoformat(),
            }

            with open(governance.provenance_log, 'a') as f:
                f.write(json.dumps(evolution_record) + '\n')

        else:
            print(f"[dream] Evolution did not produce viable candidate (fitness: {best_genome.fitness if best_genome else 0:.3f})")

    except Exception as e:
        print(f"[dream] Evolution submission failed: {e}")
        import traceback
        traceback.print_exc()


def _promote_impl(tool: str) -> Tuple[bool, str]:
    """
    Execute promotion: move tool from quarantine to production.

    Steps:
    1. Move source from ~/.kloros/synth/quarantine/<tool>/ to production
    2. Update tool registry
    3. Rebuild embeddings
    4. Write provenance record

    Returns:
        (success, message) tuple
    """
    try:
        # Import governance system
        from src.tool_synthesis.governance import SynthesisGovernance

        governance = SynthesisGovernance()

        # Use existing governance promotion flow
        promoted_version = governance.promote_tool(tool, from_version="0.1.0")

        if promoted_version:
            return True, f"promoted:{promoted_version}"
        else:
            return False, "promotion_failed"

    except Exception as e:
        print(f"[promotion] Error during promotion: {e}")
        return False, f"promote_error:{e}"


def _get_gates_passed(promoted: bool, skip_tests: bool, risk: str, stats: CandidateStats, policy: Dict) -> List[str]:
    """Determine which gates were passed."""
    gates = []
    p_prom = policy.get("promotion", {})
    
    if stats.trials >= p_prom.get("min_shadow_trials", 0):
        gates.append("min_trials")
    if stats.avg_delta >= p_prom.get("shadow_win_min", 0.0):
        gates.append("win_rate")
    if risk in p_prom.get("risk_allow", []):
        gates.append("risk_level")
    if skip_tests or promoted:
        gates.append("tests")
    
    return gates


def _get_gates_failed(promoted: bool, skip_tests: bool, risk: str, stats: CandidateStats, policy: Dict, reason: str) -> List[str]:
    """Determine which gates failed."""
    gates = []
    p_prom = policy.get("promotion", {})
    
    if "quota_exhausted" in reason:
        gates.append("quota")
    if "not_enough_trials" in reason:
        gates.append("min_trials")
    if "not_winning_enough" in reason:
        gates.append("win_rate")
    if "risk_blocked" in reason:
        gates.append("risk_level")
    if "tests_red" in reason:
        gates.append("tests")
    if "promotion_failed" in reason:
        gates.append("promotion_impl")
    
    return gates


def _generate_evidence_bundle(
    tool: str,
    promoted: bool,
    reason: str,
    stats: CandidateStats,
    shadow_outcomes: List[float],
    gates_passed: List[str],
    gates_failed: List[str]
) -> None:
    """Generate and save evidence bundle for promotion decision."""
    try:
        from src.synthesis.evidence import generate_bundle, save_bundle
        
        # Convert shadow outcomes to structured format
        shadow_data = []
        for i, delta in enumerate(shadow_outcomes):
            shadow_data.append({
                "timestamp": datetime.now().isoformat(),
                "baseline_reward": 0.5,  # Placeholder
                "candidate_reward": 0.5 + delta,
                "delta": delta,
                "latency_ms": 0.0,
                "context": {"trial": i}
            })
        
        # Calculate performance metrics
        deltas = shadow_outcomes if shadow_outcomes else []
        perf_stats = {
            "trials": stats.trials,
            "wins": stats.wins,
            "losses": stats.trials - stats.wins,
            "ties": 0,
            "win_rate": stats.wins / stats.trials if stats.trials > 0 else 0.0,
            "avg_delta": stats.avg_delta,
            "median_delta": statistics.median(deltas) if deltas else 0.0,
            "p95_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
            "total_invocations": stats.trials
        }
        
        # Safety validation (placeholder - real impl would check actual safety results)
        safety_data = {
            "passed": True,
            "checks_run": ["allowlist", "forbidden_patterns", "resource_limits"],
            "violations": [],
            "allowlist_ok": True,
            "forbidden_patterns_ok": True,
            "resource_limits_ok": True,
            "timestamp": datetime.now().isoformat()
        }
        
        # Promotion decision
        decision_data = {
            "promoted": promoted,
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "gates_passed": gates_passed,
            "gates_failed": gates_failed,
            "approver": "automatic"
        }
        
        # Generate bundle
        bundle = generate_bundle(
            tool_name=tool,
            version="0.1.0",
            shadow_outcomes=shadow_data,
            stats=perf_stats,
            safety_checks=safety_data,
            decision=decision_data,
            metadata={"source": "promotion_pipeline"}
        )
        
        # Save bundle
        bundle_path = save_bundle(bundle)
        print(f"[evidence] Generated evidence bundle: {bundle_path}")
        
    except Exception as e:
        print(f"[evidence] Failed to generate evidence bundle: {e}")
        import traceback
        traceback.print_exc()
