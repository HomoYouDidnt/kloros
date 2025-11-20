# src/dream/replay/regret.py
import json, pathlib, random
LEDGER = pathlib.Path("var/dream/ledger.jsonl")
REGRET = pathlib.Path("var/dream/regret_queue.jsonl")
REGRET.parent.mkdir(parents=True, exist_ok=True)

def harvest_failures(window=200):
    if not LEDGER.exists(): return []
    fails=[]
    for ln in LEDGER.read_text().splitlines()[-window:]:
        j=json.loads(ln)
        if not j.get("passed"):
            fails.append({"family": j.get("family"),
                          "hint": j.get("metrics",{}).get("trace_head","")})
    return fails

def enqueue_regrets():
    items = harvest_failures()
    if not items: return 0
    with REGRET.open("a") as f:
        for it in items: f.write(json.dumps(it)+"\n")
    return len(items)

def maybe_schedule_from_regret(p=0.2):
    if random.random()>p or not REGRET.exists(): return None
    lines = [json.loads(x) for x in REGRET.read_text().splitlines() if x.strip()]
    return random.choice(lines) if lines else None
