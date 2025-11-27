#!/usr/bin/env python3
"""
Add architecture knowledge documents to KLoROS RAG.

This script:
1. Loads existing RAG bundle
2. Embeds new knowledge documents
3. Adds them to the RAG
4. Saves updated bundle
"""

import sys
import json
import numpy as np
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cognition.mind.memory.embeddings import EmbeddingEngine

def load_knowledge_docs():
    """Load knowledge markdown files."""
    knowledge_dir = Path(__file__).parent / 'knowledge'

    docs = []

    # Architecture docs
    subsystems_file = knowledge_dir / 'architecture' / 'subsystems.md'
    if subsystems_file.exists():
        docs.append({
            'id': 'arch_subsystems',
            'text': subsystems_file.read_text(),
            'title': 'KLoROS Subsystems Architecture',
            'file': str(subsystems_file),
            'category': 'architecture',
            'source': 'system_knowledge',
            'section': 'architecture',
            'context': 'System architecture, subsystems, data flows, and health metrics'
        })

    # Capabilities docs
    actions_file = knowledge_dir / 'capabilities' / 'actions_registry.md'
    if actions_file.exists():
        docs.append({
            'id': 'cap_actions',
            'text': actions_file.read_text(),
            'title': 'KLoROS Actions Registry',
            'file': str(actions_file),
            'category': 'capabilities',
            'source': 'system_knowledge',
            'section': 'capabilities',
            'context': 'Available actions, limitations, and execution flow'
        })

    return docs

def main():
    print("=== Adding Knowledge to RAG ===\n")

    # Load existing RAG
    rag_bundle_path = Path('/home/kloros/rag_data/rag_store.npz')
    print(f"Loading existing RAG: {rag_bundle_path}")

    bundle = np.load(rag_bundle_path, allow_pickle=True)
    existing_embeddings = bundle['embeddings']
    metadata_bytes = np.asarray(bundle['metadata_json'], dtype=np.uint8).tobytes()
    existing_metadata = json.loads(metadata_bytes.decode('utf-8'))

    print(f"  Existing: {len(existing_metadata)} documents, {existing_embeddings.shape} embeddings")

    # Load knowledge docs
    print("\nLoading knowledge documents...")
    new_docs = load_knowledge_docs()
    print(f"  Found {len(new_docs)} knowledge documents:")
    for doc in new_docs:
        print(f"    - {doc['title']} ({len(doc['text'])} chars)")

    if not new_docs:
        print("\n⚠️  No knowledge documents found!")
        return

    # Initialize embedding engine
    print("\nInitializing embedding engine (all-MiniLM-L6-v2)...")
    embedder = EmbeddingEngine(model_name="all-MiniLM-L6-v2", device="cpu")

    # Embed new docs
    print("Embedding new documents...")
    new_texts = [doc['text'] for doc in new_docs]
    new_embeddings = np.array(embedder.embed_batch(new_texts))
    print(f"  Generated {new_embeddings.shape} embeddings")

    # Combine with existing
    print("\nCombining with existing RAG...")
    combined_embeddings = np.vstack([existing_embeddings, new_embeddings])
    combined_metadata = existing_metadata + new_docs

    print(f"  Total: {len(combined_metadata)} documents, {combined_embeddings.shape} embeddings")

    # Save updated bundle
    backup_path = rag_bundle_path.with_suffix('.npz.backup_before_knowledge')
    print(f"\nBacking up existing RAG to: {backup_path}")
    rag_bundle_path.rename(backup_path)

    print(f"Saving updated RAG to: {rag_bundle_path}")
    metadata_json = json.dumps(combined_metadata, ensure_ascii=False).encode('utf-8')
    metadata_bytes = np.frombuffer(metadata_json, dtype=np.uint8)

    np.savez_compressed(
        rag_bundle_path,
        embeddings=combined_embeddings,
        metadata_json=metadata_bytes
    )

    # Update SHA256
    import hashlib
    sha256_path = rag_bundle_path.with_suffix('.sha256')
    bundle_hash = hashlib.sha256(rag_bundle_path.read_bytes()).hexdigest()
    sha256_path.write_text(f"{bundle_hash}  {rag_bundle_path.name}\n")

    print("\n✓ Knowledge added to RAG successfully!")
    print(f"\nTest query:")
    print("  python3 -c \"from src.simple_rag import RAG; rag = RAG(bundle_path='/home/kloros/rag_data/rag_store.npz', verify_bundle_hash=False); print(rag.retrieve(query_text='What subsystems does KLoROS have?', top_k=2))\"")

if __name__ == "__main__":
    main()
