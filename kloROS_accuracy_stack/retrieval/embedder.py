"""Retrieval providers for the KLoROS accuracy stack."""
from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import faiss  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    faiss = None  # type: ignore

try:
    from sentence_transformers import SentenceTransformer  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    SentenceTransformer = None  # type: ignore

logger = logging.getLogger(__name__)

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

_EMBEDDERS: Dict[str, SentenceTransformer] = {}
_FAISS_CACHE: Dict[str, Tuple[faiss.Index, List[Dict[str, Any]]]] = {}  # type: ignore[arg-type]


def _tokenize(text: str) -> List[str]:
    return [tok for tok in re.findall(r"[a-z0-9]+", text.lower()) if tok and tok not in _STOPWORDS]


def _resolve_embedders(retrieval_cfg: Dict[str, Any]) -> Dict[str, Tuple[Optional[str], str]]:
    embedders: Dict[str, Tuple[Optional[str], str]] = {}
    raw = retrieval_cfg.get("embedders")
    if isinstance(raw, dict):
        for role in ("primary", "baseline"):
            entry = raw.get(role)
            if isinstance(entry, dict):
                name = (
                    entry.get("name")
                    or entry.get("model")
                    or entry.get("id")
                    or entry.get("provider")
                )
                path = entry.get("path") or entry.get("model_path")
                if name:
                    embedders[role] = (path, str(name))
            elif isinstance(entry, str):
                embedders[role] = (None, entry)
    if "primary" not in embedders:
        legacy = retrieval_cfg.get("embedder")
        model_path = retrieval_cfg.get("model_path")
        if isinstance(legacy, list) and legacy:
            embedders["primary"] = (model_path, str(legacy[0]))
        elif isinstance(legacy, str):
            embedders["primary"] = (model_path, str(legacy))
        else:
            embedders["primary"] = (model_path, "BAAI/bge-m3")
    if "baseline" not in embedders:
        baseline = retrieval_cfg.get("baseline_embedder")
        if isinstance(baseline, str):
            embedders["baseline"] = (None, baseline)
        else:
            embedders["baseline"] = embedders["primary"]
    return embedders


def _record_retrieval_meta(
    retrieval_cfg: Dict[str, Any],
    trace: Dict[str, Any],
    embedders: Dict[str, Tuple[Optional[str], str]],
    active_embedder: str,
) -> None:
    meta = trace.setdefault("retrieval", {})
    embedder_meta = meta.setdefault("embedders", {})
    for role, (_, name) in embedders.items():
        embedder_meta[role] = name
    meta["active_embedder"] = active_embedder
    meta["fallback_on_low_quality"] = bool(retrieval_cfg.get("fallback_on_low_quality", False))


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


def _retrieve_mock(
    question: str,
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
    *,
    query_override: Optional[str] = None,
    trace_target: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    retrieval_cfg = cfg.get("retrieval", {})
    embedders = _resolve_embedders(retrieval_cfg)
    _record_retrieval_meta(retrieval_cfg, trace, embedders, embedders["primary"][1])
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
        {"query": query, "provider": "mock"}
    )
    return results


def _get_sentence_transformer(model_path: Optional[str], model_name: str) -> SentenceTransformer:
    if SentenceTransformer is None:  # pragma: no cover - runtime requirement
        raise RuntimeError(
            "sentence-transformers is not installed; install it to use the FAISS provider"
        )
    key = model_path or model_name
    if key not in _EMBEDDERS:
        if model_path and Path(model_path).exists():
            logger.info("Loading sentence-transformer from %s", model_path)
            _EMBEDDERS[key] = SentenceTransformer(model_path)
        else:
            logger.info("Loading sentence-transformer model %s", model_name)
            _EMBEDDERS[key] = SentenceTransformer(model_name)
    return _EMBEDDERS[key]


def _load_faiss_resources(index_dir: Path) -> Tuple[faiss.Index, List[Dict[str, Any]]]:
    if faiss is None:  # pragma: no cover - runtime requirement
        raise RuntimeError("faiss is not installed; install faiss-cpu to use the FAISS provider")
    cache_key = str(index_dir.resolve())
    if cache_key in _FAISS_CACHE:
        return _FAISS_CACHE[cache_key]
    if index_dir.is_dir():
        index_path = index_dir / "index.faiss"
        meta_path = index_dir / "meta.json"
    else:
        index_path = index_dir
        meta_path = index_dir.with_suffix(".meta.json")
    if not index_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"FAISS index or metadata not found in {index_dir}")
    index = faiss.read_index(str(index_path))
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    _FAISS_CACHE[cache_key] = (index, metadata)
    return index, metadata


def _retrieve_faiss(
    question: str,
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
    *,
    query_override: Optional[str] = None,
    trace_target: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    retrieval_cfg = cfg.get("retrieval", {})
    index_dir = Path(retrieval_cfg.get("index_path", "data/index/faiss"))
    embedders = _resolve_embedders(retrieval_cfg)
    primary_path, primary_name = embedders["primary"]
    _record_retrieval_meta(retrieval_cfg, trace, embedders, primary_name)
    top_k = int(retrieval_cfg.get("top_k", 10))
    model = _get_sentence_transformer(primary_path, primary_name)
    index, meta = _load_faiss_resources(index_dir)
    query = query_override or question
    vector = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]
    vector = np.asarray(vector, dtype=np.float32)
    if vector.ndim == 1:
        vector = vector.reshape(1, -1)
    scores, indices = index.search(vector, top_k)
    results: List[Dict[str, Any]] = []
    for score, idx in zip(scores[0], indices[0], strict=False):
        if idx < 0 or idx >= len(meta):
            continue
        entry = meta[idx]
        results.append({
            "id": entry["id"],
            "text": entry["text"],
            "score": float(score),
        })
    target = trace_target if trace_target is not None else trace
    target["retrieved_ids"] = [doc["id"] for doc in results]
    target["retrieved_full"] = results
    trace.setdefault("retrieval", {}).setdefault("queries", []).append(
        {"query": query, "provider": "faiss"}
    )
    return results


def retrieve(
    question: str,
    cfg: Dict[str, Any],
    trace: Dict[str, Any],
    *,
    query_override: Optional[str] = None,
    trace_target: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    provider = cfg.get("retrieval", {}).get("provider", "mock").lower()
    try:
        if provider == "faiss":
            return _retrieve_faiss(
                question, cfg, trace, query_override=query_override, trace_target=trace_target
            )
        if provider == "mock":
            return _retrieve_mock(
                question, cfg, trace, query_override=query_override, trace_target=trace_target
            )
        raise NotImplementedError(f"Retrieval provider '{provider}' is not implemented")
    except Exception as exc:  # pragma: no cover - fallback path
        logger.warning(
            "Retrieval provider '%s' failed (%s); falling back to mock provider",
            provider,
            exc,
        )
        return _retrieve_mock(
            question, cfg, trace, query_override=query_override, trace_target=trace_target
        )
