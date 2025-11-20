"""Telemetry and performance tracking for macros."""
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
from .types import Macro, MacroTrace


def track_macro_execution(
    macro: Macro,
    params: Dict[str, Any],
    outcome: Dict[str, Any],
    cost: Dict[str, float],
    log_dir: Optional[str] = None
) -> None:
    """Track macro execution for learning and analysis.

    Args:
        macro: Executed macro
        params: Parameters used
        outcome: Execution outcome
        cost: Actual costs incurred
        log_dir: Directory for logs (default: ~/.kloros/)
    """
    # Update macro statistics
    macro.stats["uses"] = macro.stats.get("uses", 0) + 1

    if outcome.get("success", False):
        macro.stats["successes"] = macro.stats.get("successes", 0) + 1
    else:
        macro.stats["failures"] = macro.stats.get("failures", 0) + 1

    # Update running averages
    n = macro.stats["uses"]
    old_avg_latency = macro.stats.get("avg_latency_ms", 0.0)
    old_avg_tokens = macro.stats.get("avg_tokens", 0.0)

    macro.stats["avg_latency_ms"] = (
        (old_avg_latency * (n - 1) + cost.get("latency_ms", 0)) / n
    )
    macro.stats["avg_tokens"] = (
        (old_avg_tokens * (n - 1) + cost.get("tokens", 0)) / n
    )

    # Log trace
    trace = MacroTrace(
        macro_id=macro.id,
        params=params,
        outcome=outcome,
        cost=cost
    )

    _log_trace(trace, log_dir)


def _log_trace(trace: MacroTrace, log_dir: Optional[str] = None) -> None:
    """Log macro trace to file.

    Args:
        trace: Macro trace to log
        log_dir: Directory for logs
    """
    if log_dir is None:
        log_dir = os.path.expanduser("~/.kloros")

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "ra3_traces.jsonl")

    trace_entry = {
        "timestamp": trace.timestamp,
        "macro_id": trace.macro_id,
        "params": trace.params,
        "outcome": trace.outcome,
        "cost": trace.cost
    }

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace_entry) + "\n")
    except Exception as e:
        print(f"[ra3] Failed to log trace: {e}")


def get_macro_stats(
    macro_id: Optional[str] = None,
    log_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Get macro performance statistics.

    Args:
        macro_id: Optional macro ID to filter by
        log_dir: Directory with logs

    Returns:
        Statistics dictionary
    """
    if log_dir is None:
        log_dir = os.path.expanduser("~/.kloros")

    log_path = os.path.join(log_dir, "ra3_traces.jsonl")

    stats = {
        "total_executions": 0,
        "total_successes": 0,
        "total_failures": 0,
        "by_macro": {},
        "avg_latency_ms": 0.0,
        "avg_tokens": 0.0
    }

    if not os.path.exists(log_path):
        return stats

    total_latency = 0.0
    total_tokens = 0.0

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                trace = json.loads(line.strip())
                mid = trace["macro_id"]

                # Filter by macro_id if specified
                if macro_id and mid != macro_id:
                    continue

                stats["total_executions"] += 1

                if trace["outcome"].get("success", False):
                    stats["total_successes"] += 1
                else:
                    stats["total_failures"] += 1

                # Track per-macro stats
                if mid not in stats["by_macro"]:
                    stats["by_macro"][mid] = {
                        "executions": 0,
                        "successes": 0,
                        "failures": 0,
                        "avg_latency_ms": 0.0,
                        "avg_tokens": 0.0
                    }

                m_stats = stats["by_macro"][mid]
                m_stats["executions"] += 1

                if trace["outcome"].get("success", False):
                    m_stats["successes"] += 1
                else:
                    m_stats["failures"] += 1

                # Accumulate for averages
                latency = trace["cost"].get("latency_ms", 0)
                tokens = trace["cost"].get("tokens", 0)

                total_latency += latency
                total_tokens += tokens

                # Update running averages for macro
                n = m_stats["executions"]
                m_stats["avg_latency_ms"] = (
                    (m_stats["avg_latency_ms"] * (n - 1) + latency) / n
                )
                m_stats["avg_tokens"] = (
                    (m_stats["avg_tokens"] * (n - 1) + tokens) / n
                )

        # Calculate overall averages
        if stats["total_executions"] > 0:
            stats["avg_latency_ms"] = total_latency / stats["total_executions"]
            stats["avg_tokens"] = total_tokens / stats["total_executions"]

        # Calculate success rates
        for mid, m_stats in stats["by_macro"].items():
            total = m_stats["executions"]
            if total > 0:
                m_stats["success_rate"] = m_stats["successes"] / total

    except Exception as e:
        print(f"[ra3] Failed to read stats: {e}")

    return stats


def get_top_macros(
    limit: int = 5,
    sort_by: str = "success_rate",
    log_dir: Optional[str] = None
) -> list:
    """Get top performing macros.

    Args:
        limit: Number of macros to return
        sort_by: Metric to sort by (success_rate, executions, avg_latency_ms)
        log_dir: Directory with logs

    Returns:
        List of (macro_id, stats) tuples
    """
    stats = get_macro_stats(log_dir=log_dir)

    macro_list = []
    for mid, m_stats in stats["by_macro"].items():
        # Calculate success rate
        if m_stats["executions"] > 0:
            m_stats["success_rate"] = m_stats["successes"] / m_stats["executions"]
        else:
            m_stats["success_rate"] = 0.0

        macro_list.append((mid, m_stats))

    # Sort
    reverse = (sort_by != "avg_latency_ms")  # Lower is better for latency
    macro_list.sort(key=lambda x: x[1].get(sort_by, 0), reverse=reverse)

    return macro_list[:limit]
