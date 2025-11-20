#!/usr/bin/env python3
"""
Re-index RAG knowledge base with proper source tracking.

Crawls knowledge_base directory and creates embeddings for all markdown files.
"""
import sys
import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, '/home/kloros')

KNOWLEDGE_BASE_DIR = Path("/home/kloros/knowledge_base")
OUTPUT_BUNDLE = Path("/home/kloros/rag_data/rag_store.npz")
OUTPUT_METADATA = Path("/home/kloros/rag_data/metadata.json")

def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []

    for i in range(0, len(words), chunk_size - overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)

    return chunks

def extract_metadata_from_path(file_path: Path) -> Dict[str, str]:
    """Extract source category from file path."""
    rel_path = file_path.relative_to(KNOWLEDGE_BASE_DIR)
    parts = rel_path.parts

    category = parts[0] if len(parts) > 0 else "unknown"
    filename = file_path.name

    return {
        "category": category,
        "filename": filename,
        "source": str(rel_path)
    }

def index_knowledge_base():
    """Index all markdown files in knowledge base."""
    print("=" * 80)
    print("RAG Knowledge Base Re-indexing")
    print("=" * 80)
    print(f"Source: {KNOWLEDGE_BASE_DIR}")
    print(f"Output: {OUTPUT_BUNDLE}")
    print()

    # Find all markdown files
    md_files = list(KNOWLEDGE_BASE_DIR.rglob("*.md"))
    print(f"Found {len(md_files)} markdown files")

    # Process each file
    all_chunks = []
    all_metadata = []

    for md_file in md_files:
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Chunk the content
            chunks = chunk_text(content, chunk_size=512, overlap=50)

            # Create metadata for each chunk
            file_meta = extract_metadata_from_path(md_file)

            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                all_metadata.append({
                    "text": chunk,
                    "source": file_meta["source"],
                    "category": file_meta["category"],
                    "filename": file_meta["filename"],
                    "chunk_index": i,
                    "chunk_id": hashlib.md5(chunk.encode()).hexdigest()[:16]
                })

            print(f"  ✓ {file_meta['source']}: {len(chunks)} chunks")

        except Exception as e:
            print(f"  ✗ {md_file}: {e}")

    print(f"\nTotal chunks: {len(all_chunks)}")

    # Generate embeddings (dummy for now - need real embedder)
    print("\nGenerating embeddings...")
    print("⚠ Using DUMMY embeddings - need to integrate sentence-transformers")

    import numpy as np

    # Create dummy embeddings (384-dim zeros)
    # In production, use: model.encode(chunks)
    embeddings = np.zeros((len(all_chunks), 384), dtype=np.float32)

    # For now, create simple hash-based embeddings for demo
    for i, chunk in enumerate(all_chunks):
        hash_val = hash(chunk) % 1000
        embeddings[i, hash_val % 384] = 1.0

    # Save bundle
    print(f"\nSaving to {OUTPUT_BUNDLE}...")
    metadata_json = json.dumps(all_metadata)

    np.savez_compressed(
        OUTPUT_BUNDLE,
        embeddings=embeddings,
        metadata_json=metadata_json
    )

    # Save metadata separately for easy inspection
    with open(OUTPUT_METADATA, 'w') as f:
        json.dump(all_metadata, f, indent=2)

    print(f"✓ Saved {len(all_chunks)} chunks")

    # Summary by category
    print("\nChunks by category:")
    categories = {}
    for meta in all_metadata:
        cat = meta['category']
        categories[cat] = categories.get(cat, 0) + 1

    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count} chunks")

    print("\n" + "=" * 80)
    print("Re-indexing complete!")
    print("=" * 80)
    print("\n⚠ WARNING: Using dummy embeddings!")
    print("For production, integrate sentence-transformers:")
    print("  from sentence_transformers import SentenceTransformer")
    print("  model = SentenceTransformer('all-MiniLM-L6-v2')")
    print("  embeddings = model.encode(chunks)")

if __name__ == "__main__":
    index_knowledge_base()
