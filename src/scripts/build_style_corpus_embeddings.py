#!/usr/bin/env python3
"""Build GLaDOS style corpus embeddings with versioning.

One-time script to:
1. Load GLaDOS voice samples from /home/kloros/data/metadata.json
2. Embed all text using BAAI/bge-small-en-v1.5
3. Save embeddings + metadata with SHA256 checksums
4. Create FAISS index for fast similarity search

Output:
- /home/kloros/.kloros/style/corpus_embeddings.npy (N x 384)
- /home/kloros/.kloros/style/corpus_texts.json (N texts)
- /home/kloros/.kloros/style/corpus_metadata.json (versioning info)
"""

import json
import os
import hashlib
import numpy as np
from datetime import datetime
from pathlib import Path


def compute_file_sha256(filepath: str) -> str:
    """Compute SHA256 hash of file.

    Args:
        filepath: Path to file

    Returns:
        Hex digest of SHA256 hash
    """
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def load_glados_corpus(metadata_path: str) -> tuple:
    """Load GLaDOS voice samples from metadata.json.

    Args:
        metadata_path: Path to GLaDOS metadata.json

    Returns:
        Tuple of (texts, tones, ids)
    """
    with open(metadata_path, 'r') as f:
        data = json.load(f)

    texts = []
    tones = []
    ids = []

    for entry in data:
        text = entry.get('text', '').strip()
        tone = entry.get('tone', 'unknown')
        entry_id = entry.get('id', '')

        if text:  # Skip empty texts
            texts.append(text)
            tones.append(tone)
            ids.append(entry_id)

    return texts, tones, ids


def embed_texts(texts: list, model_name: str = "nomic-ai/nomic-embed-text-v1.5", trust_remote_code: bool = True, truncate_dim: int = None) -> np.ndarray:
    """Embed texts using sentence-transformers with optional Matryoshka truncation.

    Args:
        texts: List of text strings
        model_name: HuggingFace model name
        truncate_dim: Optional dimension to truncate embeddings (for Matryoshka models)

    Returns:
        Embeddings array (N x D) where D is truncate_dim if specified
    """
    print(f"Loading embedding model: {model_name}")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name, trust_remote_code=trust_remote_code)
    print(f"Embedding {len(texts)} texts...")

    # Batch encode for efficiency
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)
    embeddings = np.array(embeddings)

    # Apply Matryoshka truncation if specified
    if truncate_dim and truncate_dim < embeddings.shape[1]:
        print(f"Truncating embeddings from {embeddings.shape[1]} to {truncate_dim} dimensions (Matryoshka)")
        embeddings = embeddings[:, :truncate_dim]

    return embeddings


def save_corpus(output_dir: str, embeddings: np.ndarray, texts: list,
                tones: list, ids: list, metadata: dict):
    """Save corpus embeddings and metadata.

    Args:
        output_dir: Output directory path
        embeddings: Embedding matrix (N x D)
        texts: List of texts
        tones: List of tone labels
        ids: List of entry IDs
        metadata: Metadata dict with versioning info
    """
    os.makedirs(output_dir, exist_ok=True)

    # Save embeddings
    embeddings_path = os.path.join(output_dir, "corpus_embeddings.npy")
    np.save(embeddings_path, embeddings)
    print(f"Saved embeddings to {embeddings_path}")

    # Save texts with metadata
    texts_data = [
        {"text": text, "tone": tone, "id": entry_id}
        for text, tone, entry_id in zip(texts, tones, ids)
    ]
    texts_path = os.path.join(output_dir, "corpus_texts.json")
    with open(texts_path, 'w') as f:
        json.dump(texts_data, f, indent=2)
    print(f"Saved texts to {texts_path}")

    # Add checksums to metadata
    metadata["embeddings_sha256"] = compute_file_sha256(embeddings_path)
    metadata["texts_sha256"] = compute_file_sha256(texts_path)

    # Save metadata
    metadata_path = os.path.join(output_dir, "corpus_metadata.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata to {metadata_path}")


def main():
    """Build GLaDOS style corpus embeddings."""
    # Paths
    glados_metadata_path = "/home/kloros/data/metadata.json"
    output_dir = "/home/kloros/.kloros/style"

    print("="*60)
    print("GLaDOS Style Corpus Embedding Builder")
    print("="*60)
    print()

    # Check input file exists
    if not os.path.exists(glados_metadata_path):
        print(f"❌ GLaDOS metadata not found: {glados_metadata_path}")
        print("Please ensure metadata.json is present.")
        return 1

    # Load corpus
    print(f"Loading GLaDOS corpus from {glados_metadata_path}")
    texts, tones, ids = load_glados_corpus(glados_metadata_path)
    print(f"Loaded {len(texts)} voice samples")

    # Tone distribution
    from collections import Counter
    tone_dist = Counter(tones)
    print("\nTone distribution:")
    for tone, count in tone_dist.most_common(10):
        print(f"  {tone:20s}: {count:4d}")

    # Embed texts with Matryoshka truncation to match SSOT config
    print()
    embeddings = embed_texts(texts, model_name="nomic-ai/nomic-embed-text-v1.5", trust_remote_code=True, truncate_dim=384)
    print(f"Embedding shape: {embeddings.shape}")

    # Build metadata
    corpus_sha = compute_file_sha256(glados_metadata_path)
    metadata = {
        "embed_model": "nomic-ai/nomic-embed-text-v1.5",
        "truncate_dim": 384,
        "corpus_sha": corpus_sha,
        "corpus_source": glados_metadata_path,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "total_samples": len(texts),
        "embedding_dim": embeddings.shape[1],
        "tone_distribution": dict(tone_dist),
    }

    # Save
    print()
    save_corpus(output_dir, embeddings, texts, tones, ids, metadata)

    print()
    print("="*60)
    print("✅ Corpus embeddings built successfully")
    print("="*60)
    print(f"\nOutputs in: {output_dir}")
    print(f"  - corpus_embeddings.npy ({embeddings.shape[0]} x {embeddings.shape[1]})")
    print(f"  - corpus_texts.json")
    print(f"  - corpus_metadata.json")
    print(f"\nVersion: {metadata['version']}")
    print(f"Corpus SHA: {corpus_sha[:16]}...")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
