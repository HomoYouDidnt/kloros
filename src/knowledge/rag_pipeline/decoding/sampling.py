"""Sampling-based decoding modes (top-k and nucleus)."""

from __future__ import annotations

import random
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from src.knowledge.rag_pipeline.decoding.cisc import _citations, _snippet


def _token_probabilities(tokens: Iterable[str]) -> List[Tuple[str, float]]:
    counts = Counter(tok for tok in tokens if tok)
    total = sum(counts.values()) or 1.0
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [(token, count / total) for token, count in ranked]


def topk_generate(
    question: str,
    context: str,
    cfg: Dict[str, Any],
    doc_text: Dict[str, str],
) -> Dict[str, Any]:
    topk_cfg = cfg.get("decoding", {}).get("topk", {})
    k = int(topk_cfg.get("k", 5))
    tokens = context.split()
    snippet = _snippet(tokens[: k * 2], length=k * 2)
    answer = f"[TopK k={k}] {snippet}"
    citations = _citations(context)[:2]
    return {
        "answer": answer,
        "citations": citations,
        "meta": {"k": k, "token_count": len(tokens)},
    }


def nucleus_generate(
    question: str,
    context: str,
    cfg: Dict[str, Any],
    doc_text: Dict[str, str],
) -> Dict[str, Any]:
    nucleus_cfg = cfg.get("decoding", {}).get("nucleus", {})
    p = float(nucleus_cfg.get("p", 0.9))
    max_tokens = int(nucleus_cfg.get("max_tokens", 40))
    tokens = context.split()
    ranked = _token_probabilities(tokens)
    cumulative = 0.0
    nucleus_tokens: List[str] = []
    for token, prob in ranked:
        nucleus_tokens.append(token)
        cumulative += prob
        if cumulative >= min(1.0, max(0.0, p)):
            break
    rng = random.Random(hash((question, context, p)))
    sampled = []
    if nucleus_tokens:
        for _ in range(max_tokens):
            sampled.append(rng.choice(nucleus_tokens))
    snippet = _snippet(sampled or tokens, length=min(max_tokens, 20))
    answer = f"[Nucleus p={p:.2f}] {snippet}"
    citations = _citations(context)[:2]
    return {
        "answer": answer,
        "citations": citations,
        "meta": {"p": round(p, 3), "nucleus_size": len(nucleus_tokens)},
    }
