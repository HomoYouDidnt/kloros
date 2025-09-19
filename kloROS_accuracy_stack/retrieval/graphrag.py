"""Mock GraphRAG expansion for the accuracy stack."""
from __future__ import annotations

import itertools
import re
from collections import Counter
from typing import Any, Dict, List, Tuple

_CAP_REGEX = re.compile(r"\b[A-Z][A-Za-z0-9_-]+\b")


def _extract_terms(text: str) -> List[str]:
    caps = _CAP_REGEX.findall(text)
    if caps:
        return caps
    tokens = re.findall(r"\b[a-z]{4,}\b", text.lower())
    return [tok.title() for tok in tokens[:5]]


def graphrag_expand(
    question: str,
    reranked: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
) -> Tuple[Dict[str, Any], str]:
    provider = cfg.get("graphrag", {}).get("provider", "mock").lower()
    if provider != "mock":
        raise NotImplementedError(f"GraphRAG provider '{provider}' not implemented in mock stack")

    term_counter: Counter[str] = Counter()
    edges: Counter[Tuple[str, str]] = Counter()

    for doc in reranked[:5]:
        terms = _extract_terms(doc.get("text", ""))
        term_counter.update(terms)
        for a, b in itertools.combinations(sorted(set(terms)), 2):
            edges[(a, b)] += 1

    top_terms = [term for term, _ in term_counter.most_common(5)]
    synopsis = "; ".join(top_terms) if top_terms else "No salient entities."

    graph = {
        "nodes": [
            {"id": term, "weight": float(term_counter[term])}
            for term in top_terms
        ],
        "edges": [
            {"source": a, "target": b, "weight": float(weight)}
            for (a, b), weight in edges.items()
            if a in top_terms and b in top_terms
        ],
    }

    trace["graphrag"] = {
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "provider": provider,
    }

    return graph, synopsis
