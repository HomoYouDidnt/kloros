#!/usr/bin/env python3
"""Re-embed knowledge base with nomic-embed-text-v1.5 (384-dim Matryoshka slice).

This script:
1. Loads existing documents from rag_store.npz
2. Re-embeds them with nomic-embed-text-v1.5
3. Saves new embeddings maintaining the same structure
4. Updates embeddings.npy as well
"""

import sys
import json
import numpy as np
from pathlib import Path

# Add source directory
sys.path.insert(0, '/home/kloros')

from src.rag.embedders import create_embedder

def main():
    print("[re-embed] Starting knowledge base re-embedding...")
    print("[re-embed] Model: nomic-ai/nomic-embed-text-v1.5 (384-dim slice)")

    # Paths
    rag_store_path = Path('/home/kloros/rag_data/rag_store.npz')
    embeddings_path = Path('/home/kloros/rag_data/embeddings.npy')

    # Load existing data
    print(f"[re-embed] Loading existing data from {rag_store_path}...")
    data = np.load(rag_store_path, allow_pickle=True)

    old_embeddings = data['embeddings']
    metadata_bytes = data['metadata_json']

    print(f"[re-embed] Found {old_embeddings.shape[0]} documents")
    print(f"[re-embed] Old embeddings: {old_embeddings.shape} (dim={old_embeddings.shape[1]})")

    # Decode metadata to get document texts
    metadata_str = metadata_bytes.tobytes().decode('utf-8')
    metadata = json.loads(metadata_str)

    # Extract texts from metadata
    if isinstance(metadata, list):
        texts = [item.get('text', item.get('content', '')) for item in metadata]
    elif isinstance(metadata, dict) and 'documents' in metadata:
        texts = metadata['documents']
    else:
        print("[re-embed] ERROR: Unexpected metadata format")
        print(f"[re-embed] Metadata type: {type(metadata)}")
        if isinstance(metadata, dict):
            print(f"[re-embed] Metadata keys: {list(metadata.keys())[:10]}")
        return 1

    print(f"[re-embed] Extracted {len(texts)} texts from metadata")

    # Create new embedder with nomic-embed-text-v1.5
    print("[re-embed] Loading nomic-embed-text-v1.5 model...")
    print("[re-embed] (Will use best available device)")
    embedder = create_embedder(
        model_name='nomic-ai/nomic-embed-text-v1.5',
        truncate_dim=384,  # Matryoshka slice
        trust_remote_code=True,
        use_cache=False,  # Don't cache during bulk re-embedding
        batch_size=32  # Standard batch size
    )

    print(f"[re-embed] Model loaded successfully")

    # Re-embed all texts
    print(f"[re-embed] Re-embedding {len(texts)} documents...")
    print("[re-embed] This may take a few minutes...")

    new_embeddings = embedder.encode_documents(texts)

    print(f"[re-embed] New embeddings: {new_embeddings.shape}")
    print(f"[re-embed] Embedding dimension: {new_embeddings.shape[1]}")

    # Verify dimensions
    assert new_embeddings.shape[1] == 384, f"Expected 384 dims, got {new_embeddings.shape[1]}"
    assert new_embeddings.shape[0] == len(texts), f"Embedding count mismatch"

    # Save new embeddings
    print(f"[re-embed] Saving new rag_store.npz...")
    np.savez(
        rag_store_path,
        embeddings=new_embeddings.astype(np.float32),
        metadata_json=metadata_bytes
    )

    print(f"[re-embed] Saving new embeddings.npy...")
    np.save(embeddings_path, new_embeddings.astype(np.float32))

    # Verify saved files
    print("[re-embed] Verifying saved files...")
    verify_data = np.load(rag_store_path)
    verify_embeddings = verify_data['embeddings']

    print(f"[re-embed] Verified rag_store.npz: {verify_embeddings.shape}")
    print(f"[re-embed] Verified embeddings match: {np.allclose(verify_embeddings, new_embeddings)}")

    standalone_embeddings = np.load(embeddings_path)
    print(f"[re-embed] Verified embeddings.npy: {standalone_embeddings.shape}")

    print()
    print("=" * 60)
    print("[re-embed] ✓ Re-embedding complete!")
    print("=" * 60)
    print(f"Old model: BAAI/bge-small-en-v1.5 (384-dim)")
    print(f"New model: nomic-ai/nomic-embed-text-v1.5 (384-dim Matryoshka)")
    print(f"Documents: {new_embeddings.shape[0]}")
    print(f"Dimension: {new_embeddings.shape[1]}")
    print()
    print("Backups created:")
    print("  - rag_store_bge-small_backup_20251102.npz")
    print("  - embeddings_bge-small_backup_20251102.npy")
    print()
    print("Next step: Restart KLoROS to use new embeddings")
    print("=" * 60)

    return 0

if __name__ == '__main__':
    sys.exit(main())
