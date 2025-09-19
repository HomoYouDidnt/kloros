"""Reranker providers for the accuracy stack."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from kloROS_accuracy_stack.retrieval.embedder import _tokenize

try:
    from sentence_transformers import CrossEncoder  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    CrossEncoder = None  # type: ignore

logger = logging.getLogger(__name__)

_CROSS_ENCODERS: Dict[str, Any] = {}


def _get_cross_encoder(model_path: str | None, model_name: str) -> Any:
    if CrossEncoder is None:  # pragma: no cover - runtime requirement
        raise RuntimeError(
            "sentence-transformers is not installed; install it to use the BGE reranker"
        )
    key = model_path or model_name
    if key not in _CROSS_ENCODERS:
        if model_path and Path(model_path).exists():
            logger.info("Loading CrossEncoder from %s", model_path)
            _CROSS_ENCODERS[key] = CrossEncoder(model_path)
        else:
            logger.info("Loading CrossEncoder model %s", model_name)
            _CROSS_ENCODERS[key] = CrossEncoder(model_name)
    return _CROSS_ENCODERS[key]


def _mock_rerank(question: str, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    question_tokens = set(_tokenize(question))

    def overlap_score(doc: Dict[str, Any]) -> float:
        text_tokens = set(_tokenize(doc.get("text", "")))
        if not text_tokens:
            return 0.0
        return float(len(question_tokens & text_tokens) / len(text_tokens))

    return sorted(
        hits,
        key=lambda doc: (-overlap_score(doc), -doc.get("score", 0.0), doc.get("id", "")),
    )


def _bge_rerank(question: str, hits: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    rerank_cfg = cfg.get("rerank", {})
    model_path = rerank_cfg.get("model_path")
    model_name = rerank_cfg.get("model_name", "BAAI/bge-reranker-v2-m3")
    cross_encoder = _get_cross_encoder(model_path, model_name)
    pairs = [(question, doc.get("text", "")) for doc in hits]
    scores = cross_encoder.predict(pairs)
    enriched: List[Dict[str, Any]] = []
    for doc, score in zip(hits, scores):
        enriched.append({**doc, "rerank_score": float(score)})
    enriched.sort(key=lambda doc: -doc.get("rerank_score", doc.get("score", 0.0)))
    return enriched


def rerank(
    question: str,
    hits: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
) -> List[Dict[str, Any]]:
    provider = cfg.get("rerank", {}).get("provider", "mock").lower()
    try:
        if provider == "bge-reranker-v2-m3":
            reranked = _bge_rerank(question, hits, cfg)
        elif provider == "mock":
            reranked = _mock_rerank(question, hits)
        else:
            raise NotImplementedError(f"Reranker provider '{provider}' is not implemented")
    except Exception as exc:  # pragma: no cover - fallback path
        logger.warning(
            "Reranker provider '%s' failed (%s); falling back to mock provider",
            provider,
            exc,
        )
        reranked = _mock_rerank(question, hits)
    keep_k = int(cfg.get("rerank", {}).get("keep_top_k", len(reranked)))
    reranked = reranked[:keep_k]
    trace["reranked_full"] = reranked
    trace["reranked_ids"] = [doc.get("id") for doc in reranked]
    return reranked
