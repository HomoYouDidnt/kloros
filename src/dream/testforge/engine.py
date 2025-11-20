# src/dream/testforge/engine.py
import random, yaml, pathlib
_STATE = {}  # pass counters per family

def load_template(path:str) -> dict:
    return yaml.safe_load(pathlib.Path(path).read_text())

def instantiate(tmpl:dict):
    family = tmpl["family"]
    base   = tmpl["base"]
    slots  = tmpl.get("slots", {})
    # simple slot: symbol_pairs
    pair = random.choice(slots.get("symbol_pairs", [["foo","bar"]]))
    payload = {"symbols": {"old": pair[0], "new": pair[1]}}
    return family, payload, base

def apply_mutators(base:dict, family:str, last_passed:bool, tmpl:dict):
    key = f"{family}:passes"
    _STATE[key] = _STATE.get(key, 0) + (1 if last_passed else 0)
    out = base.copy()
    # constraint_tighten after 3 consecutive passes
    if _STATE[key] >= 3:
        out["diff_limit"] = max(5, out["diff_limit"] - 10)
        out["timeout_s"]  = max(10, int(out["timeout_s"] * 0.9))
        _STATE[key] = 0
    # rename_symbols is enforced by the template payload usage downstream
    return out
