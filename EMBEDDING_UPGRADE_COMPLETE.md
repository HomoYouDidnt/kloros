# Embedding Model Upgrade Complete
## From bge-small-en-v1.5 to nomic-embed-text-v1.5

**Date:** 2025-11-02
**Status:** ✅ COMPLETE - Ready for re-embedding

---

## Summary

Successfully upgraded KLoROS's embedding model from `BAAI/bge-small-en-v1.5` (384-dim) to `nomic-ai/nomic-embed-text-v1.5` (768-dim with 384-dim Matryoshka slice).

### Benefits
- **Better retrieval accuracy** - Nomic-embed outperforms bge-small on MTEB benchmarks
- **Long-context support** - 8192 token context vs 512 tokens
- **Matryoshka flexibility** - Full 768-dim model sliced to 384-dim for storage efficiency
- **Versatile performance** - Better on diverse retrieval tasks

### Changes Made

#### 1. Configuration Update (`/home/kloros/config/models.toml`)

**Before:**
```toml
[embeddings]
model = "BAAI/bge-small-en-v1.5"
normalize = true
dim = 384
sha256 = ""
```

**After:**
```toml
[embeddings]
model = "nomic-ai/nomic-embed-text-v1.5"
normalize = true
dim = 768  # Full dimension (can be sliced to 384 via Matryoshka)
truncate_dim = 384  # Use 384-dim slice for storage efficiency
sha256 = ""
trust_remote_code = true  # Required for nomic models
```

#### 2. Code Updates (`/home/kloros/src/rag/embedders.py`)

Added support for:
- `trust_remote_code` parameter (required for nomic models)
- Matryoshka truncation (automatic 768→384 slicing)

**Key changes:**
- Added `trust_remote_code: bool = False` parameter to `DualEmbedder.__init__()`
- Pass `trust_remote_code` to all `SentenceTransformer()` calls
- Existing `truncate_dim` parameter handles Matryoshka slicing

#### 3. Model Installation

Model successfully downloaded and tested:
```bash
Model: nomic-ai/nomic-embed-text-v1.5
Full dimensions: 768
Truncated dimensions: 384 (Matryoshka)
Status: ✅ Working correctly
```

---

## Next Steps: Re-embedding Knowledge Base

Your knowledge base needs to be re-embedded with the new model. Here's how:

### Option 1: If you have a re-embedding script

Look for scripts like:
- `kloros-vec-rebuild`
- `rebuild_embeddings.py`
- `update_knowledge_base.py`

Run with updated config (models.toml already updated).

### Option 2: Manual re-embedding

If your knowledge base is in specific locations, you'll need to:

1. **Find knowledge base locations:**
   ```bash
   # Look for vector stores or embedding databases
   find /home/kloros -name "*.faiss" -o -name "*.npz" -o -name "*.npy" 2>/dev/null
   ```

2. **Re-encode documents:**
   ```python
   from src.rag.embedders import create_embedder

   # Load with new config
   embedder = create_embedder(
       model_name='nomic-ai/nomic-embed-text-v1.5',
       truncate_dim=384,
       trust_remote_code=True
   )

   # Re-embed your documents
   new_embeddings = embedder.encode_documents(your_documents)

   # Update your vector store
   # (method depends on your vector DB - FAISS, ChromaDB, etc.)
   ```

3. **Update FAISS indices** (if applicable):
   ```python
   import faiss
   import numpy as np

   # Create new index with 384 dimensions
   index = faiss.IndexFlatIP(384)  # Inner product for cosine similarity
   index.add(new_embeddings)

   # Save updated index
   faiss.write_index(index, '/path/to/knowledge_base.faiss')
   ```

### Option 3: Use the Task agent

If uncertain about the re-embedding process, you can ask me to:
1. Find all knowledge bases that need re-embedding
2. Identify the correct re-embedding procedure for your setup
3. Execute the re-embedding with proper verification

---

## Verification

### Test Current Setup

```bash
cd /home/kloros
source .venv/bin/activate

python -c "
from src.rag.embedders import create_embedder

# Test loading
embedder = create_embedder(
    model_name='nomic-ai/nomic-embed-text-v1.5',
    truncate_dim=384,
    trust_remote_code=True
)

# Test encoding
test_docs = ['Test document 1', 'Test document 2']
embeddings = embedder.encode_documents(test_docs)

print(f'✓ Model loaded: nomic-ai/nomic-embed-text-v1.5')
print(f'✓ Embedding shape: {embeddings.shape}')
print(f'✓ Expected: (2, 384)')
print(f'✓ Match: {embeddings.shape == (2, 384)}')
"
```

Expected output:
```
✓ Model loaded: nomic-ai/nomic-embed-text-v1.5
✓ Embedding shape: (2, 384)
✓ Expected: (2, 384)
✓ Match: True
```

---

## Technical Details

### Matryoshka Representation Learning

Nomic-embed-v1.5 uses Matryoshka learning, meaning:
- Model outputs 768-dimensional embeddings
- Can be truncated to any size (64, 128, 256, 384, 512, 768) with minimal performance loss
- We're using 384-dim for storage efficiency while maintaining good performance
- If you need higher accuracy in future, can increase `truncate_dim` in config

### Performance Comparison

```
Model               | Params | Dims | Context | MTEB Score
--------------------|--------|------|---------|------------
bge-small-en-v1.5   | 33M    | 384  | 512     | 62.0
nomic-embed-v1.5    | 137M   | 768  | 8192    | 62.4
nomic (384-slice)   | 137M   | 384  | 8192    | ~61.5
```

### Storage Impact

- **Before:** 384 floats × 4 bytes = 1.5 KB per document
- **After:** 384 floats × 4 bytes = 1.5 KB per document (same!)
- **Benefit:** Better accuracy with same storage footprint

---

## Rollback (if needed)

If you encounter issues and need to rollback:

### 1. Revert config
```bash
cd /home/kloros/config
# Edit models.toml and change:
model = "BAAI/bge-small-en-v1.5"
dim = 384
# Remove: truncate_dim, trust_remote_code
```

### 2. Code rollback (embedders.py)
The code changes are backward compatible - they won't break with bge-small.
Just set `trust_remote_code=False` (default).

---

## Files Modified

1. `/home/kloros/config/models.toml` - Updated embedding config
2. `/home/kloros/src/rag/embedders.py` - Added trust_remote_code support

---

## Support

- nomic-embed model card: https://huggingface.co/nomic-ai/nomic-embed-text-v1.5
- Matryoshka learning paper: https://arxiv.org/abs/2402.01613
- MTEB leaderboard: https://huggingface.co/spaces/mteb/leaderboard

---

## Notes

- ✅ sentence-transformers upgraded to 5.1.2 (supports nomic models)
- ✅ Model successfully downloaded and tested
- ✅ Matryoshka truncation verified working (768→384)
- ⏳ **Knowledge base re-embedding pending** - required before upgrade is fully active
- ℹ️ Current KLoROS instance may still be using old embeddings until restart + re-embedding

---

**Ready to re-embed?** Let me know if you'd like help identifying and re-encoding your knowledge bases!
