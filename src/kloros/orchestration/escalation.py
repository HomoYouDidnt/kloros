import json, time
from pathlib import Path

FLAG_DIR = Path("/home/kloros/.kloros/flags")

def check_escalation_flag(kind: str) -> bool:
    f = FLAG_DIR / f"escalate_{kind}.json"
    if not f.exists():
        return False
    try:
        j = json.loads(f.read_text())
        if time.time() <= j.get("expires_at", 0):
            return True
        # expired → cleanup
        f.unlink(missing_ok=True)
        return False
    except Exception:
        f.unlink(missing_ok=True)
        return False

def clear_escalation_flag(kind: str) -> None:
    (FLAG_DIR / f"escalate_{kind}.json").unlink(missing_ok=True)
