# src/dream/schedule/ucb.py
import math, random, json, pathlib
try:
    import tomllib
except ImportError:
    import tomli as tomllib

LEDGER = pathlib.Path("var/dream/ledger.jsonl")
with open("src/dream/policy/config.toml","rb") as f:
    CFG = tomllib.load(f)
REVIEW = CFG["scheduler"]["review_pct"]; EXPLORE = CFG["scheduler"]["explore_pct"]

def _stats():
    if not LEDGER.exists(): return {}
    succ, tot, last = {}, {}, {}
    for ln in LEDGER.read_text().splitlines():
        j = json.loads(ln); fam=j.get("family")
        tot[fam] = tot.get(fam,0)+1
        succ[fam]= succ.get(fam,0)+(1 if j.get("passed") else 0)
        last[fam]= j.get("t",0)
    return {f: (succ.get(f,0), tot.get(f,0), last.get(f,0)) for f in set(tot)|set(succ)}

def pick(families:list) -> str:
    s = _stats()
    # explore?
    if random.random() < EXPLORE: return random.choice(families)
    # review? (least recent)
    if random.random() < REVIEW and s:
        unseen = [f for f in families if f not in s]
        if unseen: return random.choice(unseen)
        return min(families, key=lambda f: s.get(f,(0,0,0))[2])
    # UCB1
    if not s: return random.choice(families)
    N = sum(v[1] for v in s.values()) + 1
    best, score = None, -1
    for f in families:
        succ, tot, _ = s.get(f,(0,0,0))
        mean = succ / tot if tot else 0.0
        bonus = math.sqrt(2*math.log(N)/(tot or 1))
        sc = mean + bonus
        if sc > score: best, score = f, sc
    return best or random.choice(families)
