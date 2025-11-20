#!/usr/bin/env python3
"""
Migrate knowledge base from NPZ format to Qdrant vector store.

This script loads the existing rag_store.npz (425 documents) and populates
the Qdrant semantic memory system used by kloros_memory.
"""

import json
import sys
import uuid
import hashlib
import numpy as np
from pathlib import Path

# Add repo root to path
sys.path.insert(0, '/home/kloros')
sys.path.insert(0, '/home/kloros/src')

def string_to_uuid(s: str) -> str:
    """Convert string to deterministic UUID using MD5 hash."""
    hash_digest = hashlib.md5(s.encode()).hexdigest()
    return str(uuid.UUID(hash_digest))

def main():
    print("[migrate] Starting NPZ → Qdrant migration")
    print("[migrate] =====================================")

    # Load NPZ bundle
    npz_path = Path("/home/kloros/rag_data/rag_store.npz")
    if not npz_path.exists():
        print(f"[migrate] ERROR: NPZ file not found: {npz_path}")
        sys.exit(1)

    print(f"[migrate] Loading NPZ bundle: {npz_path}")
    bundle = np.load(npz_path, allow_pickle=True)

    # Extract embeddings
    embeddings = bundle['embeddings']
    print(f"[migrate] Loaded embeddings: {embeddings.shape}")

    # Extract metadata
    metadata_bytes = bundle['metadata_json'].tobytes()
    metadata_list = json.loads(metadata_bytes.decode('utf-8'))
    print(f"[migrate] Loaded metadata: {len(metadata_list)} documents")

    if len(metadata_list) != embeddings.shape[0]:
        print(f"[migrate] ERROR: Mismatch - {len(metadata_list)} docs vs {embeddings.shape[0]} embeddings")
        sys.exit(1)

    # Initialize Qdrant vector store
    print("[migrate] Initializing Qdrant vector store...")
    from src.kloros_memory.vector_store_qdrant import QdrantVectorStore

    vector_store = QdrantVectorStore(
        persist_directory=Path("~/.kloros/vectordb_qdrant").expanduser(),
        collection_name="kloros_memory"
    )

    # Check if already populated
    existing_count = vector_store.count()
    if existing_count > 0:
        print(f"[migrate] WARNING: Collection already has {existing_count} embeddings")
        response = input("[migrate] Clear existing data and re-migrate? (yes/no): ")
        if response.lower() != 'yes':
            print("[migrate] Migration cancelled")
            sys.exit(0)

        # Clear collection
        print("[migrate] Clearing existing collection...")
        vector_store.client.delete_collection(collection_name="kloros_memory")

        # Recreate collection
        from qdrant_client.models import Distance, VectorParams
        vector_store.client.create_collection(
            collection_name="kloros_memory",
            vectors_config=VectorParams(
                size=embeddings.shape[1],
                distance=Distance.COSINE
            )
        )
        print("[migrate] Collection cleared and recreated")

    # Migrate in batches
    BATCH_SIZE = 50
    total_docs = len(metadata_list)

    print(f"[migrate] Migrating {total_docs} documents in batches of {BATCH_SIZE}...")

    for batch_start in range(0, total_docs, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total_docs)

        batch_texts = []
        batch_ids = []
        batch_metadatas = []
        batch_embeddings = []

        for i in range(batch_start, batch_end):
            doc = metadata_list[i]

            # Use doc 'id' as unique identifier and convert to UUID
            original_id = doc.get('id', f"kb_doc_{i}")
            doc_id = string_to_uuid(original_id)

            # Prepare metadata (exclude 'text' from metadata to avoid duplication)
            # Store original ID in metadata for reference
            metadata = {
                'original_id': original_id,
                'title': doc.get('title', ''),
                'file': doc.get('file', ''),
                'category': doc.get('category', 'general'),
                'source': doc.get('source', 'knowledge_base'),
                'section': doc.get('section', ''),
                'context': doc.get('context', '')
            }

            batch_texts.append(doc['text'])
            batch_ids.append(doc_id)
            batch_metadatas.append(metadata)
            batch_embeddings.append(embeddings[i])

        # Upload batch to Qdrant
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (total_docs + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"[migrate] Batch {batch_num}/{total_batches} ({len(batch_texts)} docs)...", end=' ', flush=True)

        vector_store.add_batch(
            texts=batch_texts,
            doc_ids=batch_ids,
            metadatas=batch_metadatas,
            embeddings=batch_embeddings
        )

        print("✓")

    # Verify migration
    final_count = vector_store.count()
    print(f"\n[migrate] =====================================")
    print(f"[migrate] ✅ Migration complete!")
    print(f"[migrate] Documents migrated: {final_count}")
    print(f"[migrate] Embedding dimensions: {embeddings.shape[1]}")
    print(f"[migrate] Qdrant collection: kloros_memory")

    if final_count != total_docs:
        print(f"[migrate] ⚠️  WARNING: Expected {total_docs} docs, got {final_count}")
    else:
        print(f"[migrate] ✓ All documents successfully migrated")

if __name__ == '__main__':
    main()
