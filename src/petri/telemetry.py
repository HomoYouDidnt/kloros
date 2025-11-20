"""Telemetry and incident tracking for PETRI."""
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
from .types import PetriReport


def log_report(report: PetriReport, log_dir: Optional[str] = None) -> None:
    """Log PETRI safety report to file.

    Args:
        report: PETRI safety report
        log_dir: Directory for logs (default: ~/.kloros/)
    """
    if log_dir is None:
        log_dir = os.path.expanduser("~/.kloros")

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "petri_reports.jsonl")

    # Convert report to dict
    log_entry = report.to_dict()

    # Append to log file
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"[petri] Failed to log report: {e}")


def log_incident(
    tool_name: str,
    reason: str,
    details: Optional[Dict[str, Any]] = None,
    log_dir: Optional[str] = None
) -> None:
    """Log a safety incident.

    Args:
        tool_name: Name of tool that triggered incident
        reason: Reason for incident
        details: Additional incident details
        log_dir: Directory for logs
    """
    if log_dir is None:
        log_dir = os.path.expanduser("~/.kloros")

    os.makedirs(log_dir, exist_ok=True)
    incident_path = os.path.join(log_dir, "petri_incidents.jsonl")

    incident_entry = {
        "timestamp": datetime.now().timestamp(),
        "tool_name": tool_name,
        "reason": reason,
        "details": details or {}
    }

    try:
        with open(incident_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(incident_entry) + "\n")
    except Exception as e:
        print(f"[petri] Failed to log incident: {e}")


def get_stats(log_dir: Optional[str] = None) -> Dict[str, Any]:
    """Get PETRI statistics from logs.

    Args:
        log_dir: Directory with logs

    Returns:
        Statistics dictionary
    """
    if log_dir is None:
        log_dir = os.path.expanduser("~/.kloros")

    reports_path = os.path.join(log_dir, "petri_reports.jsonl")
    incidents_path = os.path.join(log_dir, "petri_incidents.jsonl")

    stats = {
        "total_checks": 0,
        "safe_checks": 0,
        "unsafe_checks": 0,
        "incidents": 0,
        "top_blocked_tools": {},
        "top_probe_failures": {}
    }

    # Count reports
    if os.path.exists(reports_path):
        try:
            with open(reports_path, "r", encoding="utf-8") as f:
                for line in f:
                    report = json.loads(line.strip())
                    stats["total_checks"] += 1

                    if report["safe"]:
                        stats["safe_checks"] += 1
                    else:
                        stats["unsafe_checks"] += 1

                        # Track blocked tools
                        tool = report["tool_name"]
                        stats["top_blocked_tools"][tool] = stats["top_blocked_tools"].get(tool, 0) + 1

                        # Track probe failures
                        for outcome in report["outcomes"]:
                            if not outcome["ok"]:
                                probe_name = outcome["name"]
                                stats["top_probe_failures"][probe_name] = stats["top_probe_failures"].get(probe_name, 0) + 1
        except Exception as e:
            print(f"[petri] Failed to read reports: {e}")

    # Count incidents
    if os.path.exists(incidents_path):
        try:
            with open(incidents_path, "r", encoding="utf-8") as f:
                stats["incidents"] = sum(1 for _ in f)
        except Exception as e:
            print(f"[petri] Failed to read incidents: {e}")

    return stats
