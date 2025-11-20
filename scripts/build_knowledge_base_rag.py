#!/usr/bin/env python3
"""Build RAG database from knowledge base documentation."""

import json
import sys
from pathlib import Path
import numpy as np

# Add repo root to path
sys.path.insert(0, '/home/kloros')

def read_markdown_chunks(kb_dir: Path):
    """Read markdown files and split into semantic chunks."""
    chunks = []
    
    for md_file in kb_dir.rglob("*.md"):
        content = md_file.read_text(encoding='utf-8')
        
        # Split by headers (##) for section-level chunks
        sections = content.split('\n## ')
        
        for i, section in enumerate(sections):
            if not section.strip():
                continue
                
            # First section includes title
            if i == 0 and section.startswith('# '):
                text = section
            else:
                text = '## ' + section
            
            # Clean up excessive whitespace
            text = '\n'.join(line for line in text.split('\n') if line.strip())
            
            if not text.strip():
                continue
            
            # Extract title for this chunk
            lines = text.split('\n')
            title = lines[0].replace('# ', '').replace('## ', '').strip()
            
            # Create metadata
            relative_path = md_file.relative_to(kb_dir)
            category = relative_path.parts[0] if len(relative_path.parts) > 1 else 'general'
            
            chunk_data = {
                'id': f"{md_file.stem}|{i}",
                'text': text,
                'title': title,
                'file': str(md_file),
                'category': category,
                'source': 'knowledge_base',
                'section': title,
                'context': f"KLoROS Knowledge Base | {category.title()}"
            }
            
            chunks.append(chunk_data)
    
    return chunks

def generate_embeddings_streaming(chunks, output_dir):
    """Generate embeddings in batches, streaming to disk to minimize memory usage."""
    import gc
    import tempfile
    try:
        from sentence_transformers import SentenceTransformer
        # Use SSOT config for embedding model
        sys.path.insert(0, '/home/kloros/src')
        from config.models_config import get_embedder_model, get_embedder_trust_remote_code

        model_name = get_embedder_model()
        trust_remote_code = get_embedder_trust_remote_code()

        print(f"[build] Loading embedding model: {model_name} (CPU mode)")
        model = SentenceTransformer(model_name, device='cpu', trust_remote_code=trust_remote_code)

        # Process in batches and stream to disk
        BATCH_SIZE = 50
        total_chunks = len(chunks)
        temp_files = []
        embedding_dim = None

        print(f"[build] Streaming embeddings for {total_chunks} chunks (batch size: {BATCH_SIZE})...")

        for batch_start in range(0, total_chunks, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_chunks)
            batch_chunks = chunks[batch_start:batch_end]

            texts = [chunk['text'] for chunk in batch_chunks]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (total_chunks + BATCH_SIZE - 1) // BATCH_SIZE
            print(f"[build] Batch {batch_num}/{total_batches} ({len(texts)} chunks)...", end=' ', flush=True)

            # Generate embeddings for this batch
            batch_embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

            if embedding_dim is None:
                embedding_dim = batch_embeddings.shape[1]

            # Write batch to temporary file
            temp_file = output_dir / f'embeddings_batch_{batch_num}.npy'
            np.save(temp_file, batch_embeddings)
            temp_files.append(temp_file)
            print(f"✓ written to disk")

            # Free memory immediately
            del texts
            del batch_chunks
            del batch_embeddings
            gc.collect()

        # Free model
        del model
        gc.collect()

        # Combine batch files into final embeddings
        print(f"[build] Combining {len(temp_files)} batch files...")
        all_embeddings = []
        for i, temp_file in enumerate(temp_files, 1):
            print(f"[build] Loading batch {i}/{len(temp_files)}...", end=' ', flush=True)
            batch = np.load(temp_file)
            all_embeddings.append(batch)
            print("✓")

        embeddings = np.vstack(all_embeddings)
        print(f"[build] Combined shape: {embeddings.shape}")

        # Clean up temp files
        for temp_file in temp_files:
            temp_file.unlink()
        print(f"[build] Cleaned up {len(temp_files)} temporary files")

        # Free batch list
        del all_embeddings
        gc.collect()

        return embeddings

    except ImportError:
        print("[build] ERROR: sentence-transformers not available")
        print("[build] Install with: pip install sentence-transformers")
        sys.exit(1)

def main():
    import gc
    kb_dir = Path('/home/kloros/knowledge_base')
    output_dir = Path('/home/kloros/rag_data')

    print(f"[build] Reading knowledge base from: {kb_dir}")
    chunks = read_markdown_chunks(kb_dir)
    print(f"[build] Found {len(chunks)} documentation chunks")

    if not chunks:
        print("[build] ERROR: No documentation found!")
        sys.exit(1)

    # Generate embeddings (streaming to disk to minimize memory)
    embeddings = generate_embeddings_streaming(chunks, output_dir)
    print(f"[build] Generated embeddings shape: {embeddings.shape}")

    # Backup old RAG data
    old_metadata = output_dir / 'metadata.json'
    if old_metadata.exists():
        backup_path = output_dir / 'metadata.json.portal_backup'
        old_metadata.rename(backup_path)
        print(f"[build] Backed up old metadata to: {backup_path}")

    old_bundle = output_dir / 'rag_store.npz'
    if old_bundle.exists():
        backup_path = output_dir / 'rag_store.npz.portal_backup'
        old_bundle.rename(backup_path)
        print(f"[build] Backed up old bundle to: {backup_path}")

    # Write new metadata
    metadata_path = output_dir / 'metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(chunks, f, indent=2)
    print(f"[build] Wrote metadata: {metadata_path}")

    # Free chunks from memory after writing
    chunk_count = len(chunks)
    embedding_dims = embeddings.shape[1]
    del chunks
    gc.collect()

    # Write new embeddings
    embeddings_path = output_dir / 'embeddings.npy'
    np.save(embeddings_path, embeddings)
    print(f"[build] Wrote embeddings: {embeddings_path}")

    # Create bundle (read metadata from disk instead of keeping in memory)
    metadata_bytes = metadata_path.read_bytes()
    metadata_array = np.frombuffer(metadata_bytes, dtype=np.uint8)

    bundle_path = output_dir / 'rag_store.npz'
    np.savez_compressed(bundle_path, embeddings=embeddings, metadata_json=metadata_array)
    print(f"[build] Created RAG bundle: {bundle_path}")

    # Free embeddings and metadata after bundle creation
    del embeddings
    del metadata_array
    del metadata_bytes
    gc.collect()

    # Generate checksum
    import hashlib
    digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    checksum_path = bundle_path.with_suffix('.sha256')
    checksum_path.write_text(f"{digest}  {bundle_path.name}\n")
    print(f"[build] Wrote checksum: {checksum_path}")

    print("\n[build] ✅ Knowledge base RAG database built successfully!")
    print(f"[build] Total chunks: {chunk_count}")
    print(f"[build] Embedding dimensions: {embedding_dims}")
    print(f"[build] Bundle size: {bundle_path.stat().st_size / 1024:.1f} KB")

if __name__ == '__main__':
    main()
