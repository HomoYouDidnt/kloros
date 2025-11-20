from __future__ import annotations
import os, json, time
from pathlib import Path
from dataclasses import dataclass

HOME = Path("/home/kloros")
SYM_DIR = HOME / ".kloros" / "observer" / "symptoms"
FLAG_DIR = HOME / ".kloros" / "flags"
SYM_DIR.mkdir(parents=True, exist_ok=True)
FLAG_DIR.mkdir(parents=True, exist_ok=True)

THRESHOLD = int(os.environ.get("KLR_SYMPTOM_THRESHOLD_24H", "3"))
WINDOW_S = 24 * 3600
FLAG_TTL_S = int(os.environ.get("KLR_ESCALATION_FLAG_TTL", "14400"))  # 4h default

@dataclass
class Symptom:
    kind: str
    ts: float
    meta: dict

def _bucket_path() -> Path:
    return SYM_DIR / f"{time.strftime('%Y%m%d')}.jsonl"

def record_symptom(kind: str, **meta) -> None:
    rec = {"ts": time.time(), "kind": kind, "meta": meta}
    with _bucket_path().open("a") as f:
        f.write(json.dumps(rec) + "\n")

def count_recent(kind: str) -> int:
    cutoff = time.time() - WINDOW_S
    n = 0
    for p in sorted(SYM_DIR.glob("*.jsonl"), reverse=True)[:2]:  # today + yesterday
        for line in p.read_text().splitlines():
            try:
                j = json.loads(line)
                if j.get("kind") == kind and j.get("ts", 0) >= cutoff:
                    n += 1
            except Exception:
                continue
    return n

def should_escalate(kind: str) -> bool:
    return count_recent(kind) >= THRESHOLD

def set_escalation_flag(kind: str) -> Path:
    payload = {"kind": kind, "set_at": time.time(), "expires_at": time.time() + FLAG_TTL_S}
    flag = FLAG_DIR / f"escalate_{kind}.json"
    tmp = flag.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    os.replace(tmp, flag)
    return flag
