"""Tool performance tracking and analytics."""
import time
import json
import os
import functools
import logging
from typing import Dict, Any, List, Optional
from collections import defaultdict
from dataclasses import dataclass, asdict
import statistics

log = logging.getLogger("tooltracker")

@dataclass
class ToolCall:
    """Record of a tool call."""
    tool_name: str
    args: Dict[str, Any]
    success: bool
    duration: float
    timestamp: float
    error: Optional[str] = None
    result_summary: Optional[str] = None

class ToolTracker:
    """Tracks tool usage and performance."""

    def __init__(self, log_path: str = "~/.kloros/tool_tracker.jsonl"):
        """Initialize tracker.

        Args:
            log_path: Path to JSONL log file
        """
        self.log_path = os.path.expanduser(log_path)
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        # In-memory stats
        self.call_counts = defaultdict(int)
        self.success_counts = defaultdict(int)
        self.durations = defaultdict(list)
        self.last_calls = {}

    def track_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        success: bool,
        duration: float,
        error: Optional[str] = None,
        result_summary: Optional[str] = None
    ):
        """Track a tool call.

        Args:
            tool_name: Tool name
            args: Call arguments
            success: Whether call succeeded
            duration: Duration in seconds
            error: Error message if failed
            result_summary: Summary of result
        """
        call = ToolCall(
            tool_name=tool_name,
            args=args,
            success=success,
            duration=duration,
            timestamp=time.time(),
            error=error,
            result_summary=result_summary
        )

        # Update in-memory stats
        self.call_counts[tool_name] += 1
        if success:
            self.success_counts[tool_name] += 1
        self.durations[tool_name].append(duration)
        self.last_calls[tool_name] = call

        # Log to file
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(call)) + "\n")

    def get_stats(self, tool_name: str) -> Dict[str, Any]:
        """Get statistics for a tool.

        Args:
            tool_name: Tool name

        Returns:
            Statistics dict
        """
        calls = self.call_counts.get(tool_name, 0)
        if calls == 0:
            return {
                "tool_name": tool_name,
                "call_count": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0
            }

        successes = self.success_counts.get(tool_name, 0)
        durations = self.durations.get(tool_name, [])

        return {
            "tool_name": tool_name,
            "call_count": calls,
            "success_count": successes,
            "success_rate": successes / calls if calls > 0 else 0.0,
            "avg_duration": statistics.mean(durations) if durations else 0.0,
            "min_duration": min(durations) if durations else 0.0,
            "max_duration": max(durations) if durations else 0.0,
            "last_call": asdict(self.last_calls[tool_name]) if tool_name in self.last_calls else None
        }

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all tools.

        Returns:
            Dict mapping tool names to stats
        """
        return {
            tool_name: self.get_stats(tool_name)
            for tool_name in self.call_counts.keys()
        }

    def get_top_tools(self, k: int = 10, sort_by: str = "calls") -> List[Dict[str, Any]]:
        """Get top tools by usage.

        Args:
            k: Number of tools
            sort_by: Sort key ("calls", "success_rate", "duration")

        Returns:
            List of tool stats
        """
        all_stats = self.get_all_stats()

        if sort_by == "calls":
            sorted_tools = sorted(
                all_stats.items(),
                key=lambda x: x[1]["call_count"],
                reverse=True
            )
        elif sort_by == "success_rate":
            sorted_tools = sorted(
                all_stats.items(),
                key=lambda x: x[1]["success_rate"],
                reverse=True
            )
        elif sort_by == "duration":
            sorted_tools = sorted(
                all_stats.items(),
                key=lambda x: x[1]["avg_duration"]
            )
        else:
            sorted_tools = list(all_stats.items())

        return [stats for _, stats in sorted_tools[:k]]

    def load_from_log(self):
        """Load stats from log file."""
        if not os.path.exists(self.log_path):
            return

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    call_dict = json.loads(line)
                    self.call_counts[call_dict["tool_name"]] += 1
                    if call_dict["success"]:
                        self.success_counts[call_dict["tool_name"]] += 1
                    self.durations[call_dict["tool_name"]].append(call_dict["duration"])
                except Exception:
                    continue


def track_tool(name=None):
    """Decorator to track tool execution with timing and success/failure logging.

    Args:
        name: Optional custom name for the tool (defaults to function name)

    Example:
        @track_tool()
        def my_tool(x, y):
            return x + y
    """
    def deco(fn):
        label = name or fn.__name__
        @functools.wraps(fn)
        def wrap(*a, **k):
            t0 = time.time()
            ok = True
            try:
                return fn(*a, **k)
            except Exception:
                ok = False
                raise
            finally:
                dt = round(time.time() - t0, 3)
                log.info({"tool": label, "ok": ok, "dt": dt})
        return wrap
    return deco
