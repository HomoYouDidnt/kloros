from xai.middleware import load_cfg, start_turn, log_retrieval, log_tool, finalize
from xai.explain import render
def main():
    cfg = load_cfg("config/xai.yaml")
    start_turn(query="How do I integrate TUMIX with D-REAM?", user_id="alice", mode="thunderdome",
               budgets={"tokens": 2000, "tools": 3, "latency_ms": 1200}, uncertainty=0.45)
    log_retrieval([
        {"doc_id":"doc:rag_tumix","source":"general://wiki/tumix","snippet":"TUMIX is a committee-based...", "score": 12.3},
        {"doc_id":"doc:dream_api","source":"self://code/real_evolutionary_integration.py","snippet":"D-REAM API surface...", "score": 9.1},
        {"doc_id":"doc:petri","source":"general://design/petri","snippet":"PETRI handles risky ops...", "score": 8.7},
    ])
    log_tool("fs.search", {"q":"real_evolutionary_integration"}, 0, 120, True, "Found API entry points.", 0.6, 0.05, 0.05, 0.12)
    rec = finalize("Short version: treat TUMIX as the evaluator cohort for D-REAM and gate risky ops via PETRI.",
                   ["general://wiki/tumix","self://code/real_evolutionary_integration.py"], 0.22,
                   "1) Retrieve prior art; 2) Map TUMIX roles; 3) Gate with PETRI.")
    exp = render(rec, cfg); print("EXPLANATION ->", exp["id"])
    for s in exp["sections"]:
        print(f"[{s['title']}]"); 
        if 'body' in s: print(s['body']); 
        if 'list' in s: 
            for it in s['list']: print(' -', it)
if __name__ == "__main__": main()
