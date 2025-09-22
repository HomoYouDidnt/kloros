"""Reranker providers for the accuracy stack."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from kloROS_accuracy_stack.retrieval.embedder import _tokenize

try:
    from sentence_transformers import CrossEncoder  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    CrossEncoder = None  # type: ignore

logger = logging.getLogger(__name__)

_CROSS_ENCODERS: Dict[str, Any] = {}


def _normalise_rerankers(rerank_cfg: Dict[str, Any]) -> List[str]:
    candidates = rerank_cfg.get("rerankers") or rerank_cfg.get("providers")
    if isinstance(candidates, list) and candidates:
        return [str(candidate).lower() for candidate in candidates]
    provider = rerank_cfg.get("provider")
    if provider:
        return [str(provider).lower()]
    return ["mock"]


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


def _bge_rerank(
    question: str, hits: List[Dict[str, Any]], cfg: Dict[str, Any]
) -> List[Dict[str, Any]]:
    rerank_cfg = cfg.get("rerank", {})
    model_path = rerank_cfg.get("model_path")
    model_name = rerank_cfg.get("model_name", "BAAI/bge-reranker-v2-m3")
    cross_encoder = _get_cross_encoder(model_path, model_name)
    pairs = [(question, doc.get("text", "")) for doc in hits]
    scores = cross_encoder.predict(pairs)
    enriched: List[Dict[str, Any]] = []
    for doc, score in zip(hits, scores, strict=False):
        enriched.append({**doc, "rerank_score": float(score)})
    enriched.sort(key=lambda doc: -doc.get("rerank_score", doc.get("score", 0.0)))
    return enriched


def _dispatch_rerank(
    provider: str,
    question: str,
    hits: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if provider in {"bge-reranker-v2-m3", "bge", "bge_cross_encoder"}:
        return _bge_rerank(question, hits, cfg)
    if provider == "mock":
        return _mock_rerank(question, hits)
    raise NotImplementedError(f"Reranker provider '{provider}' is not implemented")


def rerank(
    question: str,
    hits: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rerank_cfg = cfg.get("rerank", {})
    providers = _normalise_rerankers(rerank_cfg)
    attempts: List[Tuple[str, str]] = []
    reranked: List[Dict[str, Any]] | None = None
    chosen_provider = "mock"
    last_error: Exception | None = None
    for provider in providers:
        try:
            reranked = _dispatch_rerank(provider, question, hits, cfg)
            chosen_provider = provider
            break
        except Exception as exc:  # pragma: no cover - fallback path
            last_error = exc
            attempts.append((provider, str(exc)))
            logger.warning(
                "Reranker provider '%s' failed (%s)",
                provider,
                exc,
            )
            continue
    if reranked is None:
        reranked = _mock_rerank(question, hits)
        if last_error is not None:
            logger.warning(
                "Falling back to mock reranker after failures: %s",
                ", ".join(provider for provider, _ in attempts),
            )
        chosen_provider = "mock"
    keep_k = int(cfg.get("rerank", {}).get("keep_top_k", len(reranked)))
    reranked = reranked[:keep_k]
    trace["reranked_full"] = reranked
    trace["reranked_ids"] = [doc.get("id") for doc in reranked]
    rerank_meta = trace.setdefault("rerank", {})
    rerank_meta["chosen_provider"] = chosen_provider
    if attempts:
        rerank_meta["attempts"] = [provider for provider, _ in attempts]
    rerank_meta.setdefault("providers", providers)
    return reranked
