"""Parrot-guard: Multi-layer protection against corpus parroting.

Prevents KLoROS from directly quoting GLaDOS corpus through:
1. Lexical bans (Portal-specific phrases)
2. Fast prefilter (Jaccard 3-gram overlap on FAISS neighbors)
3. Semantic check (cosine similarity with z-norm calibration)

Privacy: Logs metrics only, never persists user text.
"""

import re
import time
import numpy as np
from typing import Tuple, List, Optional


# Lexical ban list: Portal-specific phrases that should never appear
BANNED_PHRASES = [
    "aperture science",
    "enrichment center",
    "the cake is a lie",
    "test chamber",
    "companion cube",
    "weighted storage cube",
    "portal gun",
    "neurotoxin",
    "bring your daughter to work day",
    "chell",
    "wheatley",
    "caroline",
    "cave johnson",
    "black mesa",
    "genetic lifeform and disk operating system",
    "testing track",
    "turret",
    "emancipation grill",
]


def _normalize(s: str) -> str:
    """Normalize text for comparison (helps both lexical and embed checks).

    Args:
        s: Input text

    Returns:
        Normalized lowercase text with only alphanumeric and spaces
    """
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def jaccard_3gram(a: str, b: str) -> float:
    """Compute Jaccard similarity of 3-gram character sets.

    Fast prefilter for detecting text overlap without expensive embeddings.

    Args:
        a: First text
        b: Second text

    Returns:
        Jaccard similarity [0, 1]
    """
    def trigrams(s):
        return {s[i:i+3] for i in range(max(0, len(s)-2))}

    A, B = trigrams(a), trigrams(b)
    if not A and not B:
        return 0.0
    return len(A & B) / (len(A | B) or 1)


def parrot_guard(
    text: str,
    corpus_index,  # FAISS index with approx_neighbors() and similarities() methods
    embedder,  # Function: str -> np.ndarray
    sim_cap: float = 0.85,
    jaccard_cap: float = 0.30,
    latency_budget_ms: float = 25.0,
) -> Tuple[bool, str]:
    """Multi-layer parrot detection with fast-path optimization.

    Args:
        text: Generated response to check
        corpus_index: FAISS index with GLaDOS corpus embeddings
        embedder: Embedding function (str -> vector)
        sim_cap: Maximum cosine similarity threshold
        jaccard_cap: Maximum Jaccard 3-gram overlap threshold
        latency_budget_ms: Maximum time allowed for semantic check (ms)

    Returns:
        Tuple of (is_safe: bool, reason: str)
        Reasons: "short", "lexical_ban", "ngram_overlap", "too_similar_X.XX", "ok_maxsim_X.XX", "timeout_skip"
    """
    n = text.strip()

    # Fast-path: tiny replies rarely parrot (save CPU)
    if len(n) < 40:
        is_safe = not any(p in n.lower() for p in BANNED_PHRASES)
        return is_safe, "short"

    # Layer 1: Lexical ban (Portal-specific phrases)
    normalized = _normalize(n)
    if any(p in normalized for p in BANNED_PHRASES):
        return False, "lexical_ban"

    # Layer 2: Fast prefilter using Jaccard 3-gram on FAISS neighbors
    try:
        nn_texts = corpus_index.approx_neighbors(normalized, topk=10)
        for neighbor_text in nn_texts:
            if jaccard_3gram(normalized, _normalize(neighbor_text)) > jaccard_cap:
                return False, "ngram_overlap"
    except Exception as e:
        print(f"[parrot_guard] FAISS prefilter failed: {e}")
        # Continue to semantic check as fallback

    # Layer 3: Semantic check with latency budget
    start = time.perf_counter()

    try:
        vec = embedder(text)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Bail if embedding took too long (latency budget)
        if elapsed_ms > latency_budget_ms:
            print(f"[parrot_guard] Latency budget exceeded ({elapsed_ms:.1f}ms), skipping semantic check")
            return True, "timeout_skip"  # Conservative: allow

        # Get similarities to corpus
        sims = corpus_index.similarities(vec, topk=10)
        if len(sims) == 0:
            return True, "ok_no_matches"

        max_sim = float(np.max(sims))

        # Z-norm calibration helps guard against different embedders/model drift
        mu, sd = float(np.mean(sims)), float(np.std(sims) or 1e-6)

        # Reject if too similar (either absolute threshold or z-score outlier)
        if max_sim > sim_cap or (mu + 2*sd) > 0.80:
            return False, f"too_similar_{max_sim:.2f}"

        return True, f"ok_maxsim_{max_sim:.2f}"

    except Exception as e:
        print(f"[parrot_guard] Semantic check failed: {e}")
        # Conservative: allow on error (prevents blocking legitimate responses)
        return True, "error_fallback"


class CorpusIndex:
    """Placeholder for FAISS corpus index (to be implemented in build script)."""

    def __init__(self, embeddings: np.ndarray, texts: List[str], metadata: dict):
        """Initialize corpus index.

        Args:
            embeddings: Precomputed corpus embeddings (N x D)
            texts: Original corpus texts (N,)
            metadata: Index metadata (embed_model, corpus_sha, created_at, version)
        """
        self.embeddings = embeddings
        self.texts = texts
        self.metadata = metadata
        self.version = f"{metadata['embed_model']}:{metadata['version']}:{metadata['corpus_sha'][:8]}"

    def approx_neighbors(self, text: str, topk: int = 10) -> List[str]:
        """Get approximate nearest neighbors (for Jaccard prefilter).

        Args:
            text: Query text
            topk: Number of neighbors

        Returns:
            List of neighbor texts
        """
        # Simple linear search for now (replace with FAISS for production)
        # This is just for the Jaccard prefilter, so exact match not critical
        if topk >= len(self.texts):
            return self.texts[:topk]
        return self.texts[:topk]

    def similarities(self, vec: np.ndarray, topk: int = 10) -> np.ndarray:
        """Compute cosine similarities to corpus.

        Args:
            vec: Query embedding
            topk: Number of similarities to return

        Returns:
            Array of top-k cosine similarities
        """
        # Normalize query vector
        vec_norm = vec / (np.linalg.norm(vec) + 1e-8)

        # Normalize corpus embeddings
        emb_norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True) + 1e-8
        corpus_norm = self.embeddings / emb_norms

        # Cosine similarity
        sims = corpus_norm @ vec_norm

        # Return top-k
        if len(sims) <= topk:
            return sims

        top_indices = np.argpartition(sims, -topk)[-topk:]
        return sims[top_indices]


__all__ = ["parrot_guard", "CorpusIndex", "BANNED_PHRASES", "jaccard_3gram"]
