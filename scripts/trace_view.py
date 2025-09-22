#!/usr/bin/env python3
"""Trace viewer for KLoROS JSON logs."""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from glob import glob
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_time_window(since_str: str) -> datetime:
    """Parse time window string like '15m', '2h', '1d' into datetime."""
    if not since_str:
        return datetime.min.replace(tzinfo=timezone.utc)

    # Extract number and unit
    try:
        if since_str.endswith("m"):
            minutes = int(since_str[:-1])
            return datetime.now(timezone.utc) - timedelta(minutes=minutes)
        elif since_str.endswith("h"):
            hours = int(since_str[:-1])
            return datetime.now(timezone.utc) - timedelta(hours=hours)
        elif since_str.endswith("d"):
            days = int(since_str[:-1])
            return datetime.now(timezone.utc) - timedelta(days=days)
        else:
            # Try to parse as integer minutes
            minutes = int(since_str)
            return datetime.now(timezone.utc) - timedelta(minutes=minutes)
    except ValueError:
        print(f"Invalid time window: {since_str}", file=sys.stderr)
        sys.exit(1)


def find_log_files(log_dir: str) -> List[Path]:
    """Find all JSON log files in directory, sorted by modification time."""
    log_path = Path(log_dir)
    if not log_path.exists():
        return []

    # Find all .jsonl files
    pattern = str(log_path / "*.jsonl")
    files = glob(pattern)

    # Sort by modification time (newest first)
    return sorted([Path(f) for f in files], key=lambda p: p.stat().st_mtime, reverse=True)


def read_log_entries(
    log_files: List[Path], since: datetime, tail: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Read log entries from files, filtered by time."""
    entries = []

    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)

                        # Parse timestamp
                        ts_str = entry.get("ts", "")
                        if ts_str:
                            try:
                                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                if ts >= since:
                                    entries.append(entry)
                            except ValueError:
                                # If timestamp parsing fails, include the entry
                                entries.append(entry)
                        else:
                            # No timestamp, include the entry
                            entries.append(entry)

                    except json.JSONDecodeError:
                        # Skip malformed JSON lines
                        continue

        except Exception as e:
            print(f"Error reading {log_file}: {e}", file=sys.stderr)
            continue

    # Sort by timestamp
    entries.sort(key=lambda e: e.get("ts", ""))

    # Apply tail limit
    if tail and len(entries) > tail:
        entries = entries[-tail:]

    return entries


def filter_entries(
    entries: List[Dict[str, Any]], trace_id: Optional[str] = None, names: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Filter entries by trace_id and event names."""
    filtered = entries

    if trace_id:
        filtered = [e for e in filtered if e.get("trace_id", "").startswith(trace_id)]

    if names:
        name_set = set(names)
        filtered = [e for e in filtered if e.get("name") in name_set]

    return filtered


def format_entry(entry: Dict[str, Any]) -> str:
    """Format a log entry for display."""
    # Extract key fields
    ts = entry.get("ts", "")
    trace_id = entry.get("trace_id", "")
    name = entry.get("name", "")

    # Format timestamp (show only time part)
    time_part = ""
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            time_part = dt.strftime("%H:%M:%S")
        except ValueError:
            time_part = ts[:8] if len(ts) >= 8 else ts

    # Format trace_id (show first 6 chars)
    trace_part = trace_id[:6] + "…" if len(trace_id) > 6 else trace_id.ljust(7)

    # Format event name (max 12 chars)
    name_part = name[:12].ljust(12)

    # Extract and format payload (excluding standard fields)
    payload_parts = []
    for key, value in entry.items():
        if key in ("ts", "level", "name", "trace_id"):
            continue

        # Format common field types
        if key == "open" and isinstance(value, bool):
            payload_parts.append(f"open={str(value)}")
        elif key == "thr" or key.endswith("_dbfs"):
            payload_parts.append(f"thr={value}")
        elif key == "conf" or key == "confidence":
            payload_parts.append(
                f"conf={value:.2f}" if isinstance(value, (int, float)) else f"conf={value}"
            )
        elif key == "lang":
            payload_parts.append(f"lang={value}")
        elif key.endswith("_ms") and isinstance(value, (int, float)):
            payload_parts.append(f"{key}={value:.0f}ms")
        elif key in ("len", "len_samples"):
            payload_parts.append(f"len={value}")
        elif key in ("in", "tokens_in", "input_length"):
            payload_parts.append(f"in={value}")
        elif key in ("out", "tokens_out"):
            payload_parts.append(f"out={value}")
        elif key == "sources" and isinstance(value, list):
            payload_parts.append(f"sources={len(value)}")
        elif key in ("transcript", "reply_text") and isinstance(value, str):
            # Show truncated text in quotes
            text = value[:30] + "..." if len(value) > 30 else value
            payload_parts.append(f'{key}="{text}"')
        elif key in ("audio_path", "tts_path") and isinstance(value, str):
            # Show just filename
            filename = Path(value).name if value else "None"
            payload_parts.append(f"out={filename}")
        elif key == "duration_s" and isinstance(value, (int, float)):
            payload_parts.append(f"{value:.1f}s")
        elif key == "ok" and isinstance(value, bool):
            payload_parts.append(f"ok={str(value)}")
        elif key == "reason":
            payload_parts.append(f"reason={value}")
        else:
            # Generic formatting
            if isinstance(value, str) and len(value) > 20:
                payload_parts.append(f"{key}={value[:20]}...")
            else:
                payload_parts.append(f"{key}={value}")

    payload_text = " ".join(payload_parts)

    return f"{time_part}Z  {trace_part}  {name_part} {payload_text}"


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="View and filter KLoROS JSON trace logs")
    parser.add_argument(
        "--dir",
        type=str,
        default=os.getenv("KLR_LOG_DIR", os.path.expanduser("~/.kloros/logs")),
        help="Log directory (default: ~/.kloros/logs)",
    )
    parser.add_argument("--since", type=str, help="Time window: 15m, 2h, 1d (default: all)")
    parser.add_argument("--trace-id", type=str, help="Filter by trace ID (prefix match)")
    parser.add_argument("--name", type=str, help="Filter by event names (comma-separated)")
    parser.add_argument("--tail", type=int, default=200, help="Show last N entries (default: 200)")

    args = parser.parse_args()

    try:
        # Parse time window
        since = (
            parse_time_window(args.since)
            if args.since
            else datetime.min.replace(tzinfo=timezone.utc)
        )

        # Find log files
        log_files = find_log_files(args.dir)
        if not log_files:
            print(f"No log files found in {args.dir}", file=sys.stderr)
            sys.exit(1)

        # Read entries
        entries = read_log_entries(log_files, since, args.tail)

        # Filter entries
        names = args.name.split(",") if args.name else None
        filtered_entries = filter_entries(entries, args.trace_id, names)

        # Display results
        if not filtered_entries:
            print("No matching log entries found.")
            return

        print(f"Showing {len(filtered_entries)} entries from {len(log_files)} log files:")
        print("TIME      TRACE     EVENT        DETAILS")
        print("-" * 80)

        for entry in filtered_entries:
            print(format_entry(entry))

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
