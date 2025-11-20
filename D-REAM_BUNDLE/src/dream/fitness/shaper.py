# src/dream/fitness/shaper.py
try:
    import tomllib
except ImportError:
    import tomli as tomllib
from src.dream.metrics.ledger import rolling_pass_rate

with open("src/dream/policy/config.toml","rb") as f:
    CFG = tomllib.load(f)
BMIN = CFG["target_band"]["min"]; BMAX = CFG["target_band"]["max"]
H = CFG["hardener"]; S = CFG["softener"]

def shape_constraints(family: str, base: dict):
    rate, n = rolling_pass_rate(family)
    shaped = base.copy()
    if n < 20: return shaped, "cold_start", rate
    if rate > BMAX:
        shaped["diff_limit"]   = max(5, base["diff_limit"] + H["diff_limit_delta"])
        shaped["timeout_s"]    = max(10, int(base["timeout_s"] * H["timeout_scale"]))
        shaped["context_lines"]= max(5,  base["context_lines"] + H["context_lines_delta"])
        return shaped, "harden", rate
    if rate < BMIN:
        shaped["diff_limit"]   = base["diff_limit"] + S["diff_limit_delta"]
        shaped["timeout_s"]    = int(base["timeout_s"] * S["timeout_scale"])
        shaped["context_lines"]= base["context_lines"] + S["context_lines_delta"]
        return shaped, "soften", rate
    return shaped, "in_band", rate
