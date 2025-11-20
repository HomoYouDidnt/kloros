#!/usr/bin/env python3
"""
Deduplicate semantic evidence capabilities using embedding similarity.

Uses the same embedding model as the runtime system (from SSOT config) to find
semantically similar capabilities and merge them, keeping the most informative version.
"""

import sys
sys.path.insert(0, '/home/kloros')  # For ssot module
sys.path.insert(0, '/home/kloros/src')  # For config module

import json
import numpy as np
from pathlib import Path
from typing import List, Tuple, Set
from collections import defaultdict

def compute_embeddings(texts: List[str], model) -> np.ndarray:
    """Compute embeddings for a list of texts."""
    if not texts:
        return np.array([])
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

def find_duplicates(
    capabilities: List[str],
    embeddings: np.ndarray,
    similarity_threshold: float = 0.85
) -> List[Set[int]]:
    """
    Find groups of semantically similar capabilities.

    Returns:
        List of sets, where each set contains indices of similar capabilities
    """
    n = len(capabilities)
    if n == 0:
        return []

    # Normalize embeddings for cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normalized = embeddings / norms

    # Compute pairwise similarity matrix
    similarity = normalized @ normalized.T

    # Find groups of similar items
    visited = set()
    groups = []

    for i in range(n):
        if i in visited:
            continue

        # Find all items similar to i
        similar_indices = set([i])
        for j in range(i + 1, n):
            if similarity[i, j] >= similarity_threshold:
                similar_indices.add(j)

        if len(similar_indices) > 1:
            groups.append(similar_indices)
            visited.update(similar_indices)

    return groups

def select_best_capability(capabilities: List[str], indices: Set[int]) -> str:
    """
    Select the best capability from a group of similar ones.

    Prefers:
    1. Longest description (most informative)
    2. More specific language (contains ":", numbers, technical terms)
    """
    candidates = [(i, capabilities[i]) for i in indices]

    # Score each candidate
    scores = []
    for i, cap in candidates:
        score = len(cap)  # Base score: length

        # Bonus for structure markers
        if ':' in cap:
            score += 20
        if any(char.isdigit() for char in cap):
            score += 10

        # Penalty for vague words
        vague_words = ['handles', 'manages', 'provides', 'supports']
        if any(word in cap.lower() for word in vague_words):
            score -= 5

        scores.append((score, i, cap))

    # Return highest scoring capability
    scores.sort(reverse=True)
    return scores[0][2]

def deduplicate_module(
    module_name: str,
    capabilities: List[str],
    model,
    similarity_threshold: float = 0.85,
    dry_run: bool = False
) -> Tuple[List[str], dict]:
    """
    Deduplicate capabilities for a single module.

    Returns:
        Tuple of (deduplicated_capabilities, stats)
    """
    if len(capabilities) == 0:
        return capabilities, {"original": 0, "deduplicated": 0, "removed": 0}

    print(f"\n[{module_name}] Analyzing {len(capabilities)} capabilities...")

    # Compute embeddings
    embeddings = compute_embeddings(capabilities, model)

    # Find duplicate groups
    duplicate_groups = find_duplicates(capabilities, embeddings, similarity_threshold)

    if not duplicate_groups:
        print(f"[{module_name}] No duplicates found")
        return capabilities, {
            "original": len(capabilities),
            "deduplicated": len(capabilities),
            "removed": 0,
            "groups": 0
        }

    # Select best from each group
    indices_to_remove = set()
    indices_to_keep = set()

    for group in duplicate_groups:
        best_cap = select_best_capability(capabilities, group)
        best_idx = capabilities.index(best_cap)

        indices_to_keep.add(best_idx)
        for idx in group:
            if idx != best_idx:
                indices_to_remove.add(idx)

        if not dry_run:
            print(f"\n  Group of {len(group)} similar capabilities:")
            print(f"    KEEP: {best_cap[:80]}...")
            for idx in group:
                if idx != best_idx:
                    print(f"    DROP: {capabilities[idx][:80]}...")

    # Build deduplicated list
    deduplicated = [
        cap for i, cap in enumerate(capabilities)
        if i not in indices_to_remove
    ]

    stats = {
        "original": len(capabilities),
        "deduplicated": len(deduplicated),
        "removed": len(indices_to_remove),
        "groups": len(duplicate_groups)
    }

    print(f"[{module_name}] Removed {stats['removed']} duplicates in {stats['groups']} groups")
    print(f"[{module_name}] {stats['original']} → {stats['deduplicated']} capabilities")

    return deduplicated, stats

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Deduplicate semantic evidence")
    parser.add_argument('--threshold', type=float, default=0.85,
                       help='Similarity threshold (0.0-1.0, default: 0.85)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be removed without making changes')
    parser.add_argument('--module', type=str,
                       help='Only process this module')
    args = parser.parse_args()

    print("=" * 60)
    print("Semantic Evidence Deduplication")
    print("=" * 60)
    print(f"Similarity threshold: {args.threshold}")
    print(f"Dry run: {args.dry_run}")

    # Load embedding model
    try:
        from sentence_transformers import SentenceTransformer

        # Load SSOT directly instead of relying on models_config fallback
        try:
            from ssot.loader import get_ssot
            ssot = get_ssot()
            model_name = ssot.get_embedder_model()
            trust_remote_code = ssot.get_embedder_trust_remote_code()
            print(f"\n✓ Loaded embedder from SSOT: {model_name}")
        except Exception as e:
            print(f"\n✗ SSOT unavailable ({e}), using fallback")
            from config.models_config import get_embedder_model, get_embedder_trust_remote_code
            model_name = get_embedder_model()
            trust_remote_code = get_embedder_trust_remote_code()

        print(f"Loading embedding model: {model_name}")
        model = SentenceTransformer(model_name, device='cpu', trust_remote_code=trust_remote_code)

        # Verify dimensions
        test_embedding = model.encode(["test"], convert_to_numpy=True)
        print(f"Embedding dimensions: {test_embedding.shape[1]}")
    except ImportError:
        print("ERROR: sentence-transformers not available")
        print("Install with: pip install sentence-transformers")
        sys.exit(1)

    # Load semantic evidence
    semantic_file = Path('/home/kloros/.kloros/semantic_evidence.json')
    if not semantic_file.exists():
        print(f"ERROR: {semantic_file} not found")
        sys.exit(1)

    with open(semantic_file) as f:
        data = json.load(f)

    print(f"\nLoaded evidence for {len(data)} modules")

    # Process each module
    total_stats = defaultdict(int)
    updated_data = {}

    modules_to_process = [args.module] if args.module else sorted(data.keys())

    for module_name in modules_to_process:
        if module_name not in data:
            print(f"\nWARNING: Module '{module_name}' not found in semantic evidence")
            continue

        module_data = data[module_name].copy()
        capabilities = module_data.get('provides_capabilities', [])

        if len(capabilities) == 0:
            print(f"\n[{module_name}] No capabilities to deduplicate")
            updated_data[module_name] = module_data
            continue

        deduplicated, stats = deduplicate_module(
            module_name,
            capabilities,
            model,
            similarity_threshold=args.threshold,
            dry_run=args.dry_run
        )

        # Update module data
        module_data['provides_capabilities'] = deduplicated
        updated_data[module_name] = module_data

        # Accumulate stats
        for key, value in stats.items():
            total_stats[key] += value

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total capabilities: {total_stats['original']}")
    print(f"After deduplication: {total_stats['deduplicated']}")
    print(f"Removed: {total_stats['removed']} ({total_stats['removed']/total_stats['original']*100:.1f}%)")
    print(f"Duplicate groups found: {total_stats['groups']}")

    if not args.dry_run:
        # Backup original
        backup_path = semantic_file.with_suffix('.json.dedup_backup')
        print(f"\nBacking up original to: {backup_path}")
        semantic_file.rename(backup_path)

        # Write deduplicated data
        print(f"Writing deduplicated data to: {semantic_file}")
        with open(semantic_file, 'w') as f:
            json.dump(updated_data, f, indent=2)

        print("\n✅ Deduplication complete!")
    else:
        print("\n[DRY RUN] No changes made. Run without --dry-run to apply changes.")

if __name__ == '__main__':
    main()
