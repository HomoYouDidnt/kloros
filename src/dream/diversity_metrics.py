"""
Diversity Metrics: MinHash and Self-BLEU

Prevents repetitive or overly similar candidates from being admitted.
Uses MinHash for parameter space diversity and Self-BLEU for output diversity.
"""
import hashlib
import json
from typing import List, Dict, Any
import numpy as np


def calculate_minhash_signature(params: Dict[str, Any], num_hashes: int = 128) -> List[int]:
    """
    Calculate MinHash signature for parameter dictionary.

    MinHash estimates Jaccard similarity efficiently by hashing parameter sets.
    """
    # Convert params to string representation
    param_str = json.dumps(params, sort_keys=True)

    # Create set of shingles (3-grams of parameter string)
    shingles = set()
    for i in range(len(param_str) - 2):
        shingles.add(param_str[i:i+3])

    # Calculate MinHash signature
    signature = []
    for seed in range(num_hashes):
        min_hash = float('inf')
        for shingle in shingles:
            # Hash with seed
            h = hashlib.sha256(f"{seed}:{shingle}".encode()).hexdigest()
            h_int = int(h[:8], 16)  # Use first 8 hex chars
            min_hash = min(min_hash, h_int)
        signature.append(min_hash)

    return signature


def minhash_jaccard_similarity(sig1: List[int], sig2: List[int]) -> float:
    """
    Estimate Jaccard similarity from MinHash signatures.

    Returns: 0.0 (completely different) to 1.0 (identical)
    """
    if len(sig1) != len(sig2):
        raise ValueError("Signatures must have same length")

    matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
    return matches / len(sig1)


def calculate_param_diversity(candidates: List[Dict[str, Any]]) -> float:
    """
    Calculate parameter space diversity using MinHash.

    Returns: 0.0 (no diversity, all identical) to 1.0 (high diversity)
    """
    if len(candidates) <= 1:
        return 1.0  # Single candidate has max diversity

    # Extract params from candidates
    params_list = [c.get("params", {}) for c in candidates]

    # Calculate MinHash signatures
    signatures = [calculate_minhash_signature(params) for params in params_list]

    # Calculate pairwise similarities
    similarities = []
    for i in range(len(signatures)):
        for j in range(i + 1, len(signatures)):
            sim = minhash_jaccard_similarity(signatures[i], signatures[j])
            similarities.append(sim)

    if not similarities:
        return 1.0

    # Diversity = 1 - mean similarity
    mean_similarity = np.mean(similarities)
    diversity = 1.0 - mean_similarity

    return float(diversity)


def calculate_self_bleu(outputs: List[str], n: int = 3) -> float:
    """
    Calculate Self-BLEU score for a set of outputs.

    Self-BLEU measures diversity by computing BLEU score between each output
    and all other outputs. Lower Self-BLEU = higher diversity.

    Returns: 0.0 (high diversity) to 1.0 (low diversity, repetitive)
    """
    if len(outputs) <= 1:
        return 0.0  # High diversity (no repetition possible)

    def get_ngrams(text: str, n: int) -> set:
        """Extract n-grams from text."""
        words = text.split()
        return set(tuple(words[i:i+n]) for i in range(len(words) - n + 1))

    # Calculate pairwise n-gram overlaps
    overlaps = []
    for i, output_i in enumerate(outputs):
        ngrams_i = get_ngrams(output_i, n)

        if not ngrams_i:
            continue

        for j, output_j in enumerate(outputs):
            if i == j:
                continue

            ngrams_j = get_ngrams(output_j, n)

            if not ngrams_j:
                continue

            # Calculate overlap (precision-like metric)
            overlap = len(ngrams_i & ngrams_j) / len(ngrams_i)
            overlaps.append(overlap)

    if not overlaps:
        return 0.0

    # Mean overlap = Self-BLEU score
    return float(np.mean(overlaps))


def has_sufficient_diversity(candidates: List[Dict[str, Any]], min_diversity: float = 0.3) -> bool:
    """
    Check if candidate set has sufficient diversity.

    Args:
        candidates: List of candidate dictionaries
        min_diversity: Minimum required diversity (0.0-1.0)

    Returns:
        True if diversity meets threshold, False otherwise
    """
    diversity = calculate_param_diversity(candidates)
    return diversity >= min_diversity


if __name__ == "__main__":
    # Test MinHash diversity
    print("=== MinHash Parameter Diversity Test ===")

    # Diverse candidates
    diverse_candidates = [
        {"params": {"beam": 1, "vad": 0.3, "temp": 0.0}},
        {"params": {"beam": 3, "vad": 0.5, "temp": 0.2}},
        {"params": {"beam": 5, "vad": 0.7, "temp": 0.5}}
    ]

    # Similar candidates
    similar_candidates = [
        {"params": {"beam": 3, "vad": 0.4, "temp": 0.1}},
        {"params": {"beam": 3, "vad": 0.4, "temp": 0.1}},
        {"params": {"beam": 3, "vad": 0.4, "temp": 0.11}}
    ]

    diverse_score = calculate_param_diversity(diverse_candidates)
    similar_score = calculate_param_diversity(similar_candidates)

    print(f"Diverse candidates: diversity={diverse_score:.3f}")
    print(f"Similar candidates: diversity={similar_score:.3f}")
    print(f"\nDiverse set has sufficient diversity (>0.3): {diverse_score >= 0.3}")
    print(f"Similar set has sufficient diversity (>0.3): {similar_score >= 0.3}")

    # Test Self-BLEU
    print("\n=== Self-BLEU Output Diversity Test ===")

    diverse_outputs = [
        "the quick brown fox jumps over the lazy dog",
        "a fast red cat runs under the sleeping mouse",
        "programming requires logic and creativity"
    ]

    repetitive_outputs = [
        "the quick brown fox",
        "the quick brown cat",
        "the quick brown dog"
    ]

    diverse_bleu = calculate_self_bleu(diverse_outputs)
    repetitive_bleu = calculate_self_bleu(repetitive_outputs)

    print(f"Diverse outputs: Self-BLEU={diverse_bleu:.3f} (lower is more diverse)")
    print(f"Repetitive outputs: Self-BLEU={repetitive_bleu:.3f} (higher is less diverse)")
