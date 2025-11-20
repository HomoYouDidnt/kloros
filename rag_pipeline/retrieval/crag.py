"""Mock CRAG corrective loop for the accuracy stack."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from rag_pipeline.retrieval.embedder import retrieve


def _prominent_token(question: str) -> str | None:
    tokens = [tok for tok in re.findall(r"[A-Za-z]+", question) if len(tok) > 3]
    if not tokens:
        return None
    tokens.sort(key=lambda t: (-len(t), t.lower()))
    return tokens[0]


def _quality(reranked: List[Dict[str, Any]]) -> float:
    if not reranked:
        return 0.0
    return sum(doc.get("score", 0.0) for doc in reranked) / len(reranked)


def need_correction(reranked: List[Dict[str, Any]], cfg: Dict[str, Any]) -> bool:
    threshold = cfg.get("crag", {}).get("quality_threshold", 0.62)
    return _quality(reranked) < threshold


def corrective_loop(
    question: str,
    reranked: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
) -> List[Dict[str, Any]]:
    provider = cfg.get("retrieval", {}).get("provider", "mock").lower()
    crag_trace = trace.setdefault("crag", {})

    supported_providers = {"mock", "faiss"}
    if provider not in supported_providers:
        crag_trace["skipped_provider"] = provider
        return reranked

    bonus = _prominent_token(question)
    expanded_query = question if bonus is None else f"{question} {bonus}"
    crag_trace["expanded_query"] = expanded_query
    alternative = retrieve(
        question,
        cfg,
        trace,
        query_override=expanded_query,
        trace_target=crag_trace.setdefault("retrieval", {}),
    )
    trace["crag_branch"] = "expanded" if alternative else "noop"
    return alternative or reranked
