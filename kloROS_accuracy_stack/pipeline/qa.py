"""Orchestrator: RAG → Rerank → CRAG → GraphRAG → Decode (SLED/CISC) → CoVe Verify."""
import argparse
import json
from typing import Any, Dict, List, Tuple

import yaml

from kloROS_accuracy_stack.decoding.cisc import cisc_generate, greedy_generate
from kloROS_accuracy_stack.decoding.sled_decoding import sled_generate
from kloROS_accuracy_stack.retrieval.crag import corrective_loop, need_correction
from kloROS_accuracy_stack.retrieval.embedder import retrieve
from kloROS_accuracy_stack.retrieval.graphrag import graphrag_expand
from kloROS_accuracy_stack.retrieval.reranker import rerank
from kloROS_accuracy_stack.verify.cove import cove_verify


def build_context(
    reranked: List[Dict[str, Any]], trace: Dict[str, Any], synopsis: str | None = None
) -> str:
    chunks: List[str] = []
    doc_text: Dict[str, str] = {}
    for doc in reranked[:5]:
        text = doc.get("text", "")
        chunks.append(text)
        doc_id = doc.get("id")
        if doc_id:
            doc_text[str(doc_id)] = text
    if synopsis:
        chunks.append("[GRAPH SYNOPSIS]\n" + synopsis)
    trace["doc_text"] = doc_text
    return "\n\n".join(chunks)

def decode(
    question: str, context: str, cfg: Dict[str, Any], trace: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    decoding_cfg = cfg.get("decoding", {})
    mode_value = decoding_cfg.get("active") or decoding_cfg.get("mode", "greedy")
    if isinstance(mode_value, list):
        mode_value = mode_value[0] if mode_value else "greedy"
    mode = str(mode_value).lower()
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
        rr = corrective_loop(question, rr, cfg, trace)
    synopsis = None
    if cfg.get("graphrag", {}).get("enabled", True):
        _, synopsis = graphrag_expand(question, rr, cfg, trace)
    context = build_context(rr, trace, synopsis)
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
