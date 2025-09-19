"""Orchestrator: RAG → Rerank → CRAG → GraphRAG → Decode (SLED/CISC) → CoVe Verify."""
import argparse, json, sys
from typing import Tuple, Dict, Any, List
from retrieval.embedder import retrieve
from retrieval.reranker import rerank
from retrieval.crag import need_correction, corrective_loop
from retrieval.graphrag import graphrag_expand
from decoding.sled_decoding import sled_generate
from decoding.cisc import cisc_generate, greedy_generate
from verify.cove import cove_verify
import yaml

def build_context(reranked: List[Dict[str, Any]], synopsis: str|None=None) -> str:
    chunks = [r.get("text", "") for r in reranked[:5]]
    if synopsis:
        chunks.append("[GRAPH SYNOPSIS]\n" + synopsis)
    return "\n\n".join(chunks)

def decode(question: str, context: str, cfg: Dict[str, Any], trace: Dict[str, Any]) -> Tuple[Dict[str,Any], Dict[str,Any]]:
    mode = cfg.get("decoding", {}).get("mode", ["greedy"])[-1]  # pick last as active for simplicity
    if mode == "sled":
        answer = sled_generate(question, context, cfg)
    elif mode == "cisc":
        answer = cisc_generate(question, context, cfg)
    else:
        answer = greedy_generate(question, context, cfg)
    trace["decode_mode"] = mode
    return answer, {"mode": mode}

def answer(question: str, cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    trace: Dict[str, Any] = {"question": question}
    hits = retrieve(question, cfg, trace)
    rr = rerank(question, hits, cfg, trace)
    if need_correction(rr, cfg):
        rr = corrective_loop(question, cfg, trace)
    synopsis = None
    if cfg.get("graphrag", {}).get("enabled", True):
        _, synopsis = graphrag_expand(question, rr, cfg, trace)
    context = build_context(rr, synopsis)
    draft, meta = decode(question, context, cfg, trace)
    final = cove_verify(question, draft, context, cfg, trace)
    return final, trace

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    ap.add_argument("--config", default="config/accuracy.yml")
    ap.add_argument("--trace", default="out/trace.json")
    ap.add_argument("--mode", default="e2e")
    args = ap.parse_args()
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    final, trace = answer(args.question, cfg)
    with open(args.trace, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2)
    print(json.dumps(final, indent=2))

if __name__ == "__main__":
    main()
