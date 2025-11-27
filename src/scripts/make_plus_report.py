#!/usr/bin/env python3
"""Generate a Scholar PLUS report with citations and reviewer notes."""
import os, sys
sys.path.insert(0, '/home/kloros')

from src.knowledge.scholar.collector import Collector
from src.knowledge.scholar.pipeline_plus import build_plus_report

def main():
    # Minimal synthetic data (replace with your real artifacts)
    episodes = [
        {"episode_id":"ep1","outcome":{"success":True,"metrics":{"score":0.9}},"turns":[{"cost":{"latency_ms":120}}]},
        {"episode_id":"ep2","outcome":{"success":False,"metrics":{"score":0.4}},"turns":[{"cost":{"latency_ms":200}}]},
        {"episode_id":"ep3","outcome":{"success":True,"metrics":{"score":0.8}},"turns":[{"cost":{"latency_ms":150}}]},
    ]
    generations = [{"gen":0,"fitness":{"score":0.52}},{"gen":1,"fitness":{"score":0.61}},{"gen":2,"fitness":{"score":0.68}}]
    macro_traces = [{"macro_id":"macro-math-eval","success":True,"cost":{"tokens":320}},{"macro_id":"macro-math-eval","success":False,"cost":{"tokens":500}}]
    petri_reports = [{"safe":True},{"safe":True},{"safe":False}]

    col = Collector()
    for e in episodes: col.add_episode(e)
    for g in generations: col.add_generation(g)
    for m in macro_traces: col.add_macro_trace(m)
    for p in petri_reports: col.add_petri_report(p)

    refs_json = "/home/kloros/examples/refs.json"
    reports_dir = "/home/kloros/reports"
    os.makedirs(reports_dir, exist_ok=True)

    out = build_plus_report(col,
                            out_dir=reports_dir,
                            title="KLoROS: PLUS Report (Citations + Reviewers)",
                            authors=["KLoROS"],
                            citations_query_terms=["agent evolution","macro reasoning","playbook context"],
                            citations_bib_path=refs_json,            # fallback and/or index into Chroma if available
                            chroma_client_or_path=None,              # set to your chroma path if desired
                            chroma_collection="citations",
                            run_reviewer=True)
    print("Wrote:", out)

if __name__ == "__main__":
    main()
