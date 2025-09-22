"""Orchestrator: RAG → Rerank → CRAG → GraphRAG → Decode (SLED/CISC) → CoVe Verify."""

import argparse
import json
from typing import Any, Dict, List, Tuple

import yaml

from kloROS_accuracy_stack.decoding.cisc import cisc_generate, greedy_generate
from kloROS_accuracy_stack.decoding.sampling import nucleus_generate, topk_generate
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
        doc_id = str(doc.get("id", "unknown"))
        chunk = "[DOC:{}]\n{}".format(doc_id, text).strip()
        chunks.append(chunk)
        doc_text[doc_id] = chunk
    if synopsis:
        chunks.append("[GRAPH SYNOPSIS]\n{}".format(synopsis))
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
    doc_text = trace.get("doc_text", {})
    llm_provider = decoding_cfg.get("llm", {}).get("provider", "local")
    requested_mode = mode
    if mode in {"sled", "cisc"} and llm_provider != "local":
        trace.setdefault("warnings", []).append(
            f"decoding: {mode} unavailable for provider {llm_provider}; falling back to greedy"
        )
        mode = "greedy"
    if mode == "sled":
        answer = sled_generate(question, context, cfg, doc_text)
    elif mode == "cisc":
        answer = cisc_generate(question, context, cfg, doc_text)
    elif mode == "topk":
        answer = topk_generate(question, context, cfg, doc_text)
    elif mode == "nucleus":
        answer = nucleus_generate(question, context, cfg, doc_text)
    else:
        answer = greedy_generate(question, context, cfg, doc_text)
    trace["decode_mode"] = mode
    if mode != requested_mode:
        trace["decode_mode_fallback"] = requested_mode
    return answer, {"mode": mode}


def answer(question: str, cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    trace: Dict[str, Any] = {"question": question}
    hits = retrieve(question, cfg, trace)
    rr = rerank(question, hits, cfg, trace)
    if need_correction(rr, cfg):
        rr = corrective_loop(question, rr, cfg, trace)
    trace["reranked_full"] = rr
    trace["reranked_ids"] = [doc.get("id") for doc in rr]
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
