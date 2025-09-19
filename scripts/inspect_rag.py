import hashlib
import json
from pathlib import Path

import numpy as np

BUNDLE_PATH = Path("rag_data/rag_store.npz")
HASH_PATH = BUNDLE_PATH.with_suffix(".sha256")
LEGACY_METADATA = Path("rag_data/metadata.json")
LEGACY_EMBEDDINGS = Path("rag_data/embeddings.npy")
FAISS_PATH = Path("rag_data/faiss.index")
PARQUET_PATH = Path("rag_data/metadata.parquet")

print("Files:")
for p in [BUNDLE_PATH, HASH_PATH, LEGACY_METADATA, LEGACY_EMBEDDINGS, FAISS_PATH, PARQUET_PATH]:
    if p.exists():
        print(f"  {p}: {p.stat().st_size:,} bytes")
    else:
        print(f"  {p}: not found")

if BUNDLE_PATH.exists():
    with np.load(BUNDLE_PATH, allow_pickle=False) as data:
        embeddings = data["embeddings"]
        metadata_bytes = np.asarray(data["metadata_json"], dtype=np.uint8).tobytes()
    metadata = json.loads(metadata_bytes.decode("utf-8"))
    bundle_label = BUNDLE_PATH
    if HASH_PATH.exists():
        expected_hash = HASH_PATH.read_text(encoding="utf-8").split()[0]
        actual_hash = hashlib.sha256(BUNDLE_PATH.read_bytes()).hexdigest()
        status = "OK" if actual_hash == expected_hash else "MISMATCH"
        print()
        print(f"Bundle hash: {actual_hash} (expected {expected_hash}) [{status}]")
else:
    if not LEGACY_METADATA.exists() or not LEGACY_EMBEDDINGS.exists():
        raise SystemExit("No bundle present and legacy files missing")
    metadata = json.loads(LEGACY_METADATA.read_text(encoding="utf-8"))
    embeddings = np.load(LEGACY_EMBEDDINGS, allow_pickle=False)
    bundle_label = "legacy JSON + NPY"

print()
print(f"Metadata source: {bundle_label}")
print("Metadata entries:", len(metadata))
if metadata:
    print("Sample metadata keys:", list(metadata[0].keys())[:10])

print()
print(
    "Embeddings shape:",
    getattr(embeddings, "shape", None),
    "dtype=",
    getattr(embeddings, "dtype", None),
)
print("First embedding norm: %.4f" % (np.linalg.norm(embeddings[0]),))
print("Embedding sample (first 5 elements):", embeddings[0][:5].tolist())
