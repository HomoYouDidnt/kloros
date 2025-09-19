"""Mock retrieval provider for the KLoROS accuracy stack."""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

# Fixture documents live inside the repo so the mock provider has deterministic data.
_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "mini" / "docs"

_STOPWORDS = {
    "the",
    "a",
    "and",
    "of",
    "to",
    "in",
    "for",
    "with",
    "on",
    "that",
    "is",
    "uses",
}


def _tokenize(text: str) -> List[str]:
    """Lowercase tokeniser with a small stopword list."""
    return [tok for tok in re.findall(r"[a-z0-9]+", text.lower()) if tok and tok not in _STOPWORDS]


@lru_cache(maxsize=1)
def _load_fixture_docs() -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for path in sorted(_FIXTURE_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        tokens = _tokenize(raw)
        tf = Counter(tokens)
        docs.append({
            "id": path.name,
            "text": raw.strip(),
            "tokens": tokens,
            "tf": tf,
        })

    # Pre-compute document frequencies for a lightweight TF-IDF weight map.
    df: Counter[str] = Counter()
    for doc in docs:
        df.update(set(doc["tokens"]))
    total_docs = max(1, len(docs))
    for doc in docs:
        weights: Dict[str, float] = {}
        for token, count in doc["tf"].items():
            idf = math.log(total_docs / (1 + df[token])) + 1.0
            weights[token] = count * idf
        doc["weights"] = weights
    return docs


def _score(tokens: List[str], weights: Dict[str, float]) -> float:
    if not tokens or not weights:
        return 0.0
    score = sum(weights.get(tok, 0.0) for tok in tokens)
    norm = max(1.0, len(tokens))
    return float(score / norm)


def retrieve(
    question: str,
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
    *,
    query_override: Optional[str] = None,
    trace_target: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return scored documents according to the configured provider."""

    provider = cfg.get("retrieval", {}).get("provider", "mock").lower()
    if provider != "mock":
        raise NotImplementedError(f"Retrieval provider '{provider}' is not implemented in mock stack")

    query = query_override or question
    target = trace_target if trace_target is not None else trace

    docs = _load_fixture_docs()
    tokens = _tokenize(query)
    scored: List[Dict[str, Any]] = []
    for doc in docs:
        score = _score(tokens, doc["weights"])
        scored.append({"id": doc["id"], "text": doc["text"], "score": score})

    scored.sort(key=lambda d: (-d["score"], d["id"]))
    top_k = int(cfg.get("retrieval", {}).get("top_k", 10))
    results = scored[:top_k]

    target["retrieved_ids"] = [doc["id"] for doc in results]
    target["retrieved_full"] = results
    trace.setdefault("retrieval", {}).setdefault("queries", []).append(
        {"query": query, "provider": provider}
    )
    return results
