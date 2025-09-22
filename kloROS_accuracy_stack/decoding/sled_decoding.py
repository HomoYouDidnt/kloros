"""Mock SLED decoding implementation for the accuracy stack."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict

from kloROS_accuracy_stack.decoding.cisc import _citations, _snippet


def sled_generate(
    question: str,
    context: str,
    cfg: Dict[str, Any],
    doc_text: Dict[str, str],
) -> Dict[str, Any]:
    sled_cfg = cfg.get("decoding", {}).get("sled", {})
    alpha = float(sled_cfg.get("alpha", 0.2))
    keep_union = int(sled_cfg.get("keep_final_topk_union", 50))

    tokens = context.split()
    midpoint = len(tokens) // 2
    mid_tokens = tokens[:midpoint]
    final_tokens = tokens[midpoint:]

    mid_counts = Counter(mid_tokens)
    final_counts = Counter(final_tokens)

    def normalised(counter: Counter[str]) -> Dict[str, float]:
        total = sum(counter.values()) or 1.0
        return {tok: count / total for tok, count in counter.items()}

    mid_probs = normalised(mid_counts)
    final_probs = normalised(final_counts)

    combined: Dict[str, float] = {}
    for tok in set(list(mid_probs.keys()) + list(final_probs.keys())):
        combined[tok] = alpha * mid_probs.get(tok, 0.0) + (1 - alpha) * final_probs.get(tok, 0.0)

    ranked_tokens = sorted(
        combined.items(),
        key=lambda item: (-item[1], item[0]),
    )
    top_tokens = [tok for tok, _ in ranked_tokens[:keep_union]]
    snippet = _snippet(top_tokens, length=16)
    energy = sum(value**2 for value in combined.values())
    answer = f"[SLED alpha={alpha:.2f}] {snippet}"
    citations = _citations(context)[:2]
    return {
        "answer": answer,
        "citations": citations,
        "meta": {"energy": round(math.sqrt(energy), 3)},
    }
