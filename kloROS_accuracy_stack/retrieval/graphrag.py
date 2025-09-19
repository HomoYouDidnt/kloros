"""GraphRAG expansion providers for the accuracy stack."""
from __future__ import annotations

import itertools
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

_CAP_REGEX = re.compile(r"\b[A-Z][A-Za-z0-9_-]+\b")


def _extract_terms(text: str) -> List[str]:
    caps = _CAP_REGEX.findall(text)
    if caps:
        return caps
    tokens = re.findall(r"\b[a-z]{4,}\b", text.lower())
    return [tok.title() for tok in tokens[:5]]


def _build_graph(reranked: List[Dict[str, Any]]) -> Dict[str, Any]:
    term_counter: Counter[str] = Counter()
    edges: Counter[Tuple[str, str]] = Counter()
    for doc in reranked[:5]:
        terms = _extract_terms(doc.get("text", ""))
        term_counter.update(terms)
        for a, b in itertools.combinations(sorted(set(terms)), 2):
            edges[(a, b)] += 1
    top_terms = [term for term, _ in term_counter.most_common(10)]
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
    synopsis = "; ".join(top_terms[:5]) if top_terms else "No salient entities."
    return graph, synopsis


def graphrag_expand(
    question: str,
    reranked: List[Dict[str, Any]],
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
) -> Tuple[Dict[str, Any], str]:
    provider = cfg.get("graphrag", {}).get("provider", "mock").lower()
    graph, synopsis = _build_graph(reranked)
    if provider == "local":
        graph_path = Path(cfg.get("graphrag", {}).get("graph_path", "data/graph/graph.json"))
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        graph_path.write_text(json.dumps({
            "question": question,
            "graph": graph,
        }, indent=2), encoding="utf-8")
    elif provider != "mock":
        raise NotImplementedError(f"GraphRAG provider '{provider}' not implemented")

    trace["graphrag"] = {
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "provider": provider,
    }

    return graph, synopsis
