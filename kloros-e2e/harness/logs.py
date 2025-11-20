"""Log monitoring for E2E tests."""
import glob
import json
import time
from pathlib import Path

from .util import cfg


def _latest_log_path() -> Path | None:
    """Find the most recent log file matching the glob pattern."""
    pattern = Path(cfg("structured_log_glob")).expanduser()
    paths = sorted(pattern.parent.glob(pattern.name))
    return paths[-1] if paths else None


def wait_for_final_response(timeout_s: int = 12) -> dict | None:
    """
    Tail the latest log file and wait for a final_response phase entry.

    Args:
        timeout_s: Maximum time to wait in seconds

    Returns:
        dict with final_response log entry, or None if not found
    """
    path = _latest_log_path()
    if not path:
        print(f"[logs] No log file found matching {cfg('structured_log_glob')}")
        return None

    print(f"[logs] Monitoring {path} for final_response...")

    t0 = time.time()

    # First check the last few lines for a recent final_response (in case it was already written)
    try:
        recent_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-10:]
        for line in reversed(recent_lines):
            try:
                obj = json.loads(line)
                # Check if this is a very recent final_response (within last 5 seconds)
                if obj.get("phase") == "final_response":
                    from datetime import datetime
                    ts_str = obj.get("ts", "")
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace('+00:00', '+00:00'))
                        age = (datetime.now(ts.tzinfo) - ts).total_seconds()
                        if age < 5:  # Entry less than 5 seconds old
                            print(f"[logs] Found recent final_response: {obj.get('final_text', '')[:80]}...")
                            return obj
            except Exception:
                continue
    except Exception:
        pass

    # If not found in recent entries, tail the file for new entries
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        # Seek to end of file
        f.seek(0, 2)

        while time.time() - t0 < timeout_s:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue

            try:
                obj = json.loads(line)
            except Exception:
                continue

            # Look for phase="final_response"
            if obj.get("phase") == "final_response":
                print(f"[logs] Found final_response: {obj.get('final_text', '')[:80]}...")
                return obj

    print(f"[logs] Timeout waiting for final_response after {timeout_s}s")
    return None
