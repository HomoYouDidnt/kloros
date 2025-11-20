"""Corpus loader with version checking and lazy initialization."""

import json
import os
import numpy as np
from pathlib import Path
from typing import Optional

from .parrot_guard import CorpusIndex


# Global singleton
_CORPUS_INDEX: Optional[CorpusIndex] = None


def load_corpus_index(corpus_dir: str = "/home/kloros/.kloros/style") -> CorpusIndex:
    """Load GLaDOS corpus index with version checking (singleton pattern).

    Args:
        corpus_dir: Directory containing corpus files

    Returns:
        Corpus index instance

    Raises:
        FileNotFoundError: If corpus files not found
        ValueError: If version mismatch detected
    """
    global _CORPUS_INDEX

    # Return cached instance if already loaded
    if _CORPUS_INDEX is not None:
        return _CORPUS_INDEX

    print("[style] Loading GLaDOS corpus index...")

    # Check files exist
    embeddings_path = os.path.join(corpus_dir, "corpus_embeddings.npy")
    texts_path = os.path.join(corpus_dir, "corpus_texts.json")
    metadata_path = os.path.join(corpus_dir, "corpus_metadata.json")

    if not os.path.exists(embeddings_path):
        raise FileNotFoundError(f"Corpus embeddings not found: {embeddings_path}")
    if not os.path.exists(texts_path):
        raise FileNotFoundError(f"Corpus texts not found: {texts_path}")
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Corpus metadata not found: {metadata_path}")

    # Load metadata
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)

    # Version checking - get expected model from SSOT config
    from src.config.models_config import get_embedder_model
    required_embed_model = get_embedder_model()
    if metadata.get("embed_model") != required_embed_model:
        raise ValueError(
            f"Corpus embed_model mismatch: "
            f"expected {required_embed_model}, got {metadata.get('embed_model')}"
        )

    # Load embeddings
    embeddings = np.load(embeddings_path)
    print(f"[style] Loaded embeddings: {embeddings.shape}")

    # Load texts
    with open(texts_path, 'r') as f:
        texts_data = json.load(f)
    texts = [entry["text"] for entry in texts_data]

    # Create index
    _CORPUS_INDEX = CorpusIndex(embeddings, texts, metadata)
    print(f"[style] Corpus index ready: {len(texts)} samples, version {metadata['version']}")

    return _CORPUS_INDEX


def get_corpus_index() -> Optional[CorpusIndex]:
    """Get cached corpus index (returns None if not loaded).

    Returns:
        Corpus index or None
    """
    return _CORPUS_INDEX


__all__ = ["load_corpus_index", "get_corpus_index"]
