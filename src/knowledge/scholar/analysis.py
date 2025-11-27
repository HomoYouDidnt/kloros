import statistics as stats
def summarize_episodes(episodes):
    if not episodes: return {"n":0, "success_rate":0.0, "avg_score":0.0, "avg_latency_ms":0.0}
    n = len(episodes)
    succ = sum(1 for e in episodes if e.get("outcome",{}).get("success"))
    scores = [e.get("outcome",{}).get("metrics",{}).get("score", 0.0) for e in episodes]
    lat = [e.get("turns",[{"cost":{"latency_ms":0}}])[-1].get("cost",{}).get("latency_ms",0) for e in episodes]
    return {"n": n, "success_rate": round(100*succ/n, 2), "avg_score": round(stats.mean(scores) if scores else 0.0, 3),
            "avg_latency_ms": round(stats.mean(lat) if lat else 0.0, 1)}
def compare_generations(gens):
    if not gens: return {"n":0, "best_gen": None, "best_fitness": None}
    best = max(gens, key=lambda g: g.get("fitness",{}).get("score",0))
    return {"n": len(gens), "best_gen": best.get("gen"), "best_fitness": best.get("fitness")}
def macro_usage(macro_traces):
    by_id = {}
    for mt in macro_traces:
        mid = mt.get("macro_id","unknown")
        by_id.setdefault(mid, {"uses":0, "wins":0, "avg_cost":0.0})
        d = by_id[mid]; d["uses"] += 1
        if mt.get("success"): d["wins"] += 1
        d["avg_cost"] += mt.get("cost",{}).get("tokens",0.0)
    for mid, d in by_id.items():
        if d["uses"]: d["avg_cost"] = round(d["avg_cost"]/d["uses"], 2)
        d["win_rate"] = round(100*(d["wins"]/d["uses"]), 2) if d["uses"] else 0.0
    return {"per_macro": by_id}
def safety_summary(reports):
    total = len(reports)
    blocked = sum(1 for r in reports if not r.get("safe", True))
    return {"total_reports": total, "blocked": blocked, "blocked_rate": (round(100*blocked/total,2) if total else 0.0)}
