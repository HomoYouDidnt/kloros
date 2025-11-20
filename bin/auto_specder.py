#!/usr/bin/env python3
"""
Auto-Spec Expansion - Phase 4

Monitors metrics & handoffs → writes new specs to toolgen/specs/auto/.
"""
from __future__ import annotations
import json, time, re
from pathlib import Path
from statistics import median

METRICS = Path("/home/kloros/logs/dream/metrics.jsonl")
AUTO_DIR = Path("/home/kloros/toolgen/specs/auto")
AUTO_DIR.mkdir(parents=True, exist_ok=True)
HANDOFF = Path("/tmp/repairlab_queue/processed")
STATE_FILE = AUTO_DIR / ".state.json"

def load_state() -> dict:
    """Load persistent state to avoid duplicate proposals."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"proposed": [], "last_run": 0}

def save_state(state: dict):
    """Save state to disk."""
    STATE_FILE.write_text(json.dumps(state, indent=2))

def load_toolgen_metrics(last_n=200):
    """Load recent ToolGen metrics."""
    rows = []
    if not METRICS.exists():
        return rows

    for line in METRICS.read_text().splitlines()[-last_n:]:
        try:
            j = json.loads(line)
            if j.get("domain") == "toolgen":
                rows.append(j)
        except:
            pass
    return rows

def plateau_trigger(rows, threshold=0.85, window=10):
    """Detect fitness plateau."""
    xs = [r.get("fitness", 0.0) for r in rows][-window:]
    if len(xs) < window:
        return False
    return median(xs) < threshold

def diversity_collapse(rows, window=10, eps=0.6):
    """Detect diversity collapse (low impl_style variety)."""
    styles = [r.get("impl_style") for r in rows][-window:]
    if len(styles) < window:
        return False
    uniq = len(set(styles)) / float(len(styles))
    return uniq < eps

def frequent_handoffs(k=5):
    """Detect high failure rate."""
    if not HANDOFF.exists():
        return False
    return len(list(HANDOFF.glob("handoff_*.fail"))) > k

def next_id(prefix: str) -> str:
    """Generate unique spec ID."""
    t = int(time.time())
    return f"{prefix}_{t}"

def write_spec(obj: dict):
    """Write spec to auto directory."""
    p = AUTO_DIR / f'{obj["id"]}.json'
    p.write_text(json.dumps(obj, indent=2))
    print(f"[auto_specder] ✓ Wrote {p}")

def propose_normalize_whitespace():
    """Propose whitespace normalization spec."""
    sid = next_id("normalize_whitespace")
    return {
        "id": sid,
        "task": "Normalize whitespace in text: collapse spaces, trim edges, preserve newlines.",
        "language": "python",
        "io": {
            "inputs": [{"name": "text", "type": "string"}],
            "output": {"type": "string"}
        },
        "constraints": {
            "time_budget_ms": 150,
            "memory_budget_mb": 64,
            "max_deps": [],
            "forbidden_calls": []
        },
        "examples": [
            {"in": {"text": "a   b"}, "out": "a b"},
            {"in": {"text": " a\n\n b "}, "out": "a\n\nb"}
        ],
        "properties": [
            {"name": "idempotent", "type": "boolean", "value": True},
            {"name": "no_mutation", "type": "boolean", "value": True}
        ],
        "origin": {"reason": "auto_expansion", "epoch_hint": None, "ts": time.time()}
    }

def propose_json_merge():
    """Propose JSON merge spec."""
    sid = next_id("json_merge")
    return {
        "id": sid,
        "task": "Deep merge two JSON objects, with second overriding first on conflicts.",
        "language": "python",
        "io": {
            "inputs": [
                {"name": "obj1", "type": "dict"},
                {"name": "obj2", "type": "dict"}
            ],
            "output": {"type": "dict"}
        },
        "constraints": {
            "time_budget_ms": 200,
            "memory_budget_mb": 128,
            "max_deps": [],
            "forbidden_calls": []
        },
        "examples": [
            {"in": {"obj1": {"a": 1}, "obj2": {"b": 2}}, "out": {"a": 1, "b": 2}},
            {"in": {"obj1": {"a": 1, "c": 3}, "obj2": {"a": 2}}, "out": {"a": 2, "c": 3}}
        ],
        "properties": [
            {"name": "idempotent", "type": "boolean", "value": False},
            {"name": "no_mutation", "type": "boolean", "value": True}
        ],
        "origin": {"reason": "auto_expansion", "epoch_hint": None, "ts": time.time()}
    }

def main():
    state = load_state()
    rows = load_toolgen_metrics()

    # Check triggers
    trig_plateau = plateau_trigger(rows)
    trig_diversity = diversity_collapse(rows)
    trig_handoffs = frequent_handoffs()

    trigger_active = trig_plateau or trig_diversity or trig_handoffs

    if not trigger_active:
        print("[auto_specder] No triggers active")
        print(f"  Plateau: {trig_plateau}")
        print(f"  Diversity collapse: {trig_diversity}")
        print(f"  Frequent handoffs: {trig_handoffs}")
        return 0

    print("[auto_specder] Triggers detected:")
    if trig_plateau:
        print("  ✓ Fitness plateau")
    if trig_diversity:
        print("  ✓ Diversity collapse")
    if trig_handoffs:
        print("  ✓ Frequent handoffs")

    # Propose new specs (rotate through proposals)
    proposals = [propose_normalize_whitespace, propose_json_merge]
    idx = len(state["proposed"]) % len(proposals)
    spec = proposals[idx]()

    # Check if already proposed
    if spec["id"].split("_")[0] + "_" + spec["id"].split("_")[1] in "_".join(state["proposed"]):
        print(f"[auto_specder] Already proposed similar spec, skipping")
        return 0

    write_spec(spec)
    state["proposed"].append(spec["id"])
    state["last_run"] = time.time()
    save_state(state)

    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
