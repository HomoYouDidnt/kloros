"""
Real Metrics Collection for KLoROS Dashboard

Connects to actual data sources:
- PHASE reports (phase_report.jsonl)
- Pytest results (.pytest_cache)
- D-REAM ledger
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
from collections import Counter, defaultdict


def get_phase_metrics(phase_report: str = "/home/kloros/src/phase/phase_report.jsonl") -> Dict[str, Any]:
    """
    Parse PHASE report for test results.

    Returns:
        Dict with PHASE test statistics
    """
    if not os.path.exists(phase_report):
        return {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "pass_rate": 0.0,
            "domains": {}
        }

    try:
        results = []
        domains = defaultdict(lambda: {"total": 0, "passed": 0})

        with open(phase_report) as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                    status = entry.get("status", "unknown")
                    domain = entry.get("params", {}).get("domain", "unknown")

                    results.append({
                        "test_id": entry.get("test_id"),
                        "status": status,
                        "domain": domain,
                        "score": entry.get("score", 0.0)
                    })

                    domains[domain]["total"] += 1
                    if status == "pass":
                        domains[domain]["passed"] += 1

                except json.JSONDecodeError:
                    continue

        total = len(results)
        passed = sum(1 for r in results if r["status"] == "pass")

        return {
            "total_tests": total,
            "passed_tests": passed,
            "failed_tests": total - passed,
            "pass_rate": round(passed / total, 3) if total > 0 else 0.0,
            "domains": dict(domains),
            "recent_results": results[-10:]  # Last 10 results
        }

    except IOError:
        return {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "pass_rate": 0.0,
            "domains": {}
        }


def get_pytest_metrics(kloros_root: str = "/home/kloros") -> Dict[str, Any]:
    """
    Parse pytest cache and test files for real test counts.

    Returns:
        Dict with pytest statistics by family
    """
    test_dir = Path(kloros_root) / "tests"
    cache_dir = Path(kloros_root) / ".pytest_cache"

    if not test_dir.exists():
        return {"total_tests": 0, "passed_tests": 0, "pass_rate": 0.0, "families": {}}

    # Count test files by directory/family
    families = defaultdict(lambda: {"total": 0, "passed": 0, "family": ""})

    # Map directories to family names
    family_map = {
        "unit": "Unit Tests",
        "integration": "Integration Tests",
        "": "Core Tests"  # Root tests directory
    }

    for test_file in test_dir.rglob("test_*.py"):
        # Determine family from path
        relative = test_file.relative_to(test_dir)
        family_key = str(relative.parent) if relative.parent != Path('.') else ""

        family_name = family_map.get(family_key, family_key.replace("/", " ").title() or "Core Tests")

        # Count test functions in file
        try:
            with open(test_file) as f:
                content = f.read()
                # Simple count of "def test_" functions
                test_count = content.count("\ndef test_") + content.count("\n    def test_")

                families[family_key]["total"] += test_count
                families[family_key]["family"] = family_name
                # For now, assume all pass (we'd need to actually run pytest to get failures)
                families[family_key]["passed"] += test_count
        except:
            continue

    # Check pytest cache for last failed
    failed_tests = set()
    lastfailed_file = cache_dir / "v" / "cache" / "lastfailed"
    if lastfailed_file.exists():
        try:
            with open(lastfailed_file) as f:
                failed_data = json.load(f)
                failed_tests = set(failed_data.keys())
        except:
            pass

    # Adjust passed counts based on failures
    for test_path in failed_tests:
        # Extract family from test path
        if "tests/unit/" in test_path:
            families["unit"]["passed"] = max(0, families["unit"]["passed"] - 1)
        elif "tests/integration/" in test_path:
            families["integration"]["passed"] = max(0, families["integration"]["passed"] - 1)
        else:
            families[""]["passed"] = max(0, families[""]["passed"] - 1)

    total = sum(f["total"] for f in families.values())
    passed = sum(f["passed"] for f in families.values())

    return {
        "total_tests": total,
        "passed_tests": passed,
        "pass_rate": round(passed / total, 3) if total > 0 else 0.0,
        "families": {k: v for k, v in families.items() if v["total"] > 0}
    }


def get_combined_test_metrics() -> Dict[str, Any]:
    """
    Combine PHASE and pytest metrics.

    Returns:
        Dict with complete test statistics
    """
    phase = get_phase_metrics()
    pytest = get_pytest_metrics()

    # Create family breakdown
    families = {}

    # Add pytest families
    for key, data in pytest.get("families", {}).items():
        fam_key = f"pytest_{key}" if key else "pytest_core"
        families[fam_key] = {
            "total": data["total"],
            "passed": data["passed"],
            "family": data["family"]
        }

    # Add PHASE as its own family
    if phase["total_tests"] > 0:
        families["phase_e2e"] = {
            "total": phase["total_tests"],
            "passed": phase["passed_tests"],
            "family": "PHASE E2E"
        }

    # Calculate totals
    total = pytest["total_tests"] + phase["total_tests"]
    passed = pytest["passed_tests"] + phase["passed_tests"]

    return {
        "total_tests": total,
        "passed_tests": passed,
        "pass_rate": round(passed / total, 3) if total > 0 else 0.0,
        "families": families,
        "phase_details": {
            "total": phase["total_tests"],
            "passed": phase["passed_tests"],
            "domains": phase.get("domains", {})
        }
    }


# Original functions (preserved for compatibility)

def get_evidence_metrics(base_dir: str = "/home/kloros/.kloros/synth/evidence") -> Dict[str, Any]:
    """Collect metrics from evidence bundles."""
    base_path = Path(base_dir)

    if not base_path.exists():
        return {
            "total_tools": 0,
            "promoted_tools": 0,
            "declined_tools": 0,
            "avg_win_rate": 0.0,
            "avg_trials": 0,
            "recent_promotions": []
        }

    promotions = []
    declined = []

    for tool_dir in base_path.iterdir():
        if not tool_dir.is_dir():
            continue

        for version_dir in tool_dir.iterdir():
            if not version_dir.is_dir():
                continue

            bundle_path = version_dir / "bundle.json"
            if not bundle_path.exists():
                continue

            try:
                with open(bundle_path) as f:
                    bundle = json.load(f)

                decision = bundle.get("decision", {})
                perf = bundle.get("performance", {})

                item = {
                    "tool": bundle.get("tool_name"),
                    "version": bundle.get("version"),
                    "promoted": decision.get("promoted", False),
                    "win_rate": perf.get("win_rate", 0.0),
                    "trials": perf.get("trials", 0),
                    "created_at": bundle.get("created_at"),
                    "reason": decision.get("decision_reason", "")
                }

                if item["promoted"]:
                    promotions.append(item)
                else:
                    declined.append(item)

            except (json.JSONDecodeError, IOError):
                continue

    all_tools = promotions + declined
    total = len(all_tools)
    promoted_count = len(promotions)

    avg_win_rate = 0.0
    avg_trials = 0
    if total > 0:
        avg_win_rate = sum(t["win_rate"] for t in all_tools) / total
        avg_trials = int(sum(t["trials"] for t in all_tools) / total)

    recent = sorted(promotions, key=lambda x: x.get("created_at", ""), reverse=True)[:10]

    return {
        "total_tools": total,
        "promoted_tools": promoted_count,
        "declined_tools": len(declined),
        "avg_win_rate": round(avg_win_rate, 3),
        "avg_trials": avg_trials,
        "recent_promotions": recent
    }


def get_quota_metrics(state_file: str = "/home/kloros/.kloros/quota_state.json") -> Dict[str, Any]:
    """Read current quota state."""
    if not os.path.exists(state_file):
        return {
            "daily_limit": 0,
            "used_today": 0,
            "remaining": 0,
            "last_reset": None
        }

    try:
        with open(state_file) as f:
            state = json.load(f)

        used = state.get("used_today", 0)
        limit = state.get("daily_limit", 100)

        return {
            "daily_limit": limit,
            "used_today": used,
            "remaining": max(0, limit - used),
            "last_reset": state.get("last_reset")
        }
    except (json.JSONDecodeError, IOError):
        return {
            "daily_limit": 0,
            "used_today": 0,
            "remaining": 0,
            "last_reset": None
        }


def get_dream_metrics(ledger_path: str = "/home/kloros/var/dream/ledger.jsonl") -> Dict[str, Any]:
    """Parse D-REAM evolution ledger for metrics."""
    if not os.path.exists(ledger_path):
        return {
            "total_generations": 0,
            "total_candidates": 0,
            "avg_fitness": 0.0,
            "success_rate": 0.0,
            "outcomes": {}
        }

    try:
        generations = []
        fitnesses = []
        outcomes = Counter()

        with open(ledger_path) as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)

                    if "generation" in entry:
                        generations.append(entry["generation"])

                    if "fitness" in entry:
                        fitnesses.append(entry["fitness"])

                    if "outcome" in entry:
                        outcomes[entry["outcome"]] += 1

                except json.JSONDecodeError:
                    continue

        total_candidates = len(fitnesses)
        avg_fitness = sum(fitnesses) / total_candidates if total_candidates > 0 else 0.0

        successful = outcomes.get("promoted", 0) + outcomes.get("improved", 0)
        total_outcomes = sum(outcomes.values())
        success_rate = successful / total_outcomes if total_outcomes > 0 else 0.0

        return {
            "total_generations": len(set(generations)),
            "total_candidates": total_candidates,
            "avg_fitness": round(avg_fitness, 3),
            "success_rate": round(success_rate, 3),
            "outcomes": dict(outcomes)
        }
    except IOError:
        return {
            "total_generations": 0,
            "total_candidates": 0,
            "avg_fitness": 0.0,
            "success_rate": 0.0,
            "outcomes": {}
        }


def get_synthesis_metrics(synth_log: str = "/home/kloros/.kloros/tool_synthesis.log") -> Dict[str, Any]:
    """Parse tool synthesis log for creation/failure stats."""
    if not os.path.exists(synth_log):
        return {
            "total_attempts": 0,
            "successful": 0,
            "failed": 0,
            "success_rate": 0.0,
            "recent_attempts": []
        }

    try:
        attempts = []

        with open(synth_log) as f:
            for line in f:
                if not line.strip():
                    continue

                if "synthesized tool:" in line.lower():
                    attempts.append({"status": "success", "line": line.strip()[:100]})
                elif "synthesis failed" in line.lower() or "error" in line.lower():
                    attempts.append({"status": "failed", "line": line.strip()[:100]})

        successful = sum(1 for a in attempts if a["status"] == "success")
        failed = len(attempts) - successful
        success_rate = successful / len(attempts) if attempts else 0.0

        return {
            "total_attempts": len(attempts),
            "successful": successful,
            "failed": failed,
            "success_rate": round(success_rate, 3),
            "recent_attempts": attempts[-10:]
        }
    except IOError:
        return {
            "total_attempts": 0,
            "successful": 0,
            "failed": 0,
            "success_rate": 0.0,
            "recent_attempts": []
        }


def get_all_metrics() -> Dict[str, Any]:
    """Aggregate all system metrics with real data."""
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "evidence": get_evidence_metrics(),
        "quota": get_quota_metrics(),
        "dream": get_dream_metrics(),
        "tests": get_combined_test_metrics(),  # Now uses real data!
        "synthesis": get_synthesis_metrics(),
        "proposals": get_improvement_proposals_metrics(),
        "candidate_queues": get_candidate_queue_metrics()
    }

def get_improvement_proposals_metrics(
    proposals_file: str = "/home/kloros/var/dream/proposals/improvement_proposals.jsonl"
) -> Dict[str, Any]:
    """Parse improvement proposals for metrics."""
    if not os.path.exists(proposals_file):
        return {
            "total_proposals": 0,
            "by_component": {},
            "by_priority": {},
            "by_status": {},
            "recent_proposals": []
        }

    try:
        proposals = []
        by_component = Counter()
        by_priority = Counter()
        by_status = Counter()

        with open(proposals_file) as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    proposal = json.loads(line)
                    proposals.append(proposal)

                    by_component[proposal.get("component", "unknown")] += 1
                    by_priority[proposal.get("priority", "unknown")] += 1
                    by_status[proposal.get("status", "unknown")] += 1

                except json.JSONDecodeError:
                    continue

        # Sort by timestamp descending
        proposals.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return {
            "total_proposals": len(proposals),
            "by_component": dict(by_component),
            "by_priority": dict(by_priority),
            "by_status": dict(by_status),
            "recent_proposals": proposals[:10]  # Last 10
        }
    except IOError:
        return {
            "total_proposals": 0,
            "by_component": {},
            "by_priority": {},
            "by_status": {},
            "recent_proposals": []
        }


def get_candidate_queue_metrics() -> Dict[str, Any]:
    """Get metrics for D-REAM candidate queues."""
    tool_queue_file = "/home/kloros/src/dream/artifacts/tool_synthesis_queue.jsonl"
    processed_log_file = "/home/kloros/src/dream/artifacts/tool_synthesis_processed.jsonl"
    phase_raw_dir = Path("/home/kloros/src/dream/artifacts/phase_raw")

    # Load processed tool names
    processed_tools = set()
    if os.path.exists(processed_log_file):
        try:
            with open(processed_log_file) as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            processed_tools.add(entry.get("tool_name"))
                        except json.JSONDecodeError:
                            continue
        except IOError:
            pass

    tool_queue_count = 0
    tool_by_status = Counter()

    # Count UNPROCESSED items in tool synthesis queue
    if os.path.exists(tool_queue_file):
        try:
            with open(tool_queue_file) as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            tool_name = entry.get("tool_name")

                            # Only count if not already processed
                            if tool_name not in processed_tools:
                                tool_queue_count += 1
                                tool_by_status[entry.get("status", "unknown")] += 1
                        except json.JSONDecodeError:
                            continue
        except IOError:
            pass

    # Count proposal candidates
    proposal_candidates = 0
    if phase_raw_dir.exists():
        for candidate_file in phase_raw_dir.glob("*.jsonl"):
            try:
                with open(candidate_file) as f:
                    for line in f:
                        if line.strip():
                            try:
                                json.loads(line)  # Validate JSON
                                proposal_candidates += 1
                            except json.JSONDecodeError:
                                continue
            except IOError:
                continue

    return {
        "tool_synthesis_queue": tool_queue_count,
        "proposal_candidates": proposal_candidates,
        "total_pending": tool_queue_count + proposal_candidates,
        "tool_by_status": dict(tool_by_status)
    }
