"""Mock reranker implementation for the accuracy stack."""
from __future__ import annotations

from typing import Any, Dict, List

from kloROS_accuracy_stack.retrieval.embedder import _tokenize


def rerank(
    question: str,
    hits: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
) -> List[Dict[str, Any]]:
    provider = cfg.get("rerank", {}).get("provider", "mock").lower()
    if provider != "mock":
        raise NotImplementedError(f"Reranker provider '{provider}' not available in mock stack")

    question_tokens = set(_tokenize(question))

    def overlap_score(doc: Dict[str, Any]) -> float:
        text_tokens = set(_tokenize(doc.get("text", "")))
        if not text_tokens:
            return 0.0
        return float(len(question_tokens & text_tokens) / len(text_tokens))

    reranked = sorted(
        hits,
        key=lambda doc: (-overlap_score(doc), -doc.get("score", 0.0), doc.get("id", "")),
    )

    keep_k = int(cfg.get("rerank", {}).get("keep_top_k", len(reranked)))
    reranked = reranked[:keep_k]

    trace["reranked_full"] = reranked
    trace["reranked_ids"] = [doc.get("id") for doc in reranked]
    return reranked
