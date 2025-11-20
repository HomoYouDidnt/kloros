"""Reciprocal Rank Fusion for combining retrieval results."""
from typing import List, Dict, Any, Optional


def reciprocal_rank_fusion(
    results_a: List[str],
    results_b: List[str],
    k: int = 60
) -> Dict[str, float]:
    """Combine two ranked lists using Reciprocal Rank Fusion.

    RRF formula: score(d) = sum(1 / (k + rank(d)))

    Args:
        results_a: First ranked list of IDs
        results_b: Second ranked list of IDs
        k: Constant for RRF (default: 60)

    Returns:
        Dict mapping ID to combined score
    """
    scores = {}

    # Score from first list
    for rank, doc_id in enumerate(results_a):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)

    # Score from second list
    for rank, doc_id in enumerate(results_b):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)

    return scores


def fuse_and_rank(
    results_a: List[str],
    results_b: List[str],
    k: int = 60,
    top_n: Optional[int] = None
) -> List[str]:
    """Fuse and return top-ranked IDs.

    Args:
        results_a: First ranked list
        results_b: Second ranked list
        k: RRF constant
        top_n: Number of top results to return (None = all)

    Returns:
        List of IDs ranked by fused score
    """
    scores = reciprocal_rank_fusion(results_a, results_b, k)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    if top_n is not None:
        ranked = ranked[:top_n]

    return [doc_id for doc_id, _ in ranked]
