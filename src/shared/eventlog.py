from __future__ import annotations
import os, json, time
from pathlib import Path
LOG = Path(os.path.expanduser("~/kloros_loop/structured.jsonl"))
LOG.parent.mkdir(parents=True, exist_ok=True)

def emit(event: str, **fields):
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event}
    rec.update(fields)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
