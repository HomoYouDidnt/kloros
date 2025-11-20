"""Pack RAG metadata + embeddings into a secure .npz bundle."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Optional

import numpy as np


def _read_metadata(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8")
    # Ensure the payload parses as JSON for sanity before packing
    json.loads(text)
    return text.encode("utf-8")


def _read_embeddings(path: Path) -> np.ndarray:
    lower = path.name.lower()
    if lower.endswith(".npy"):
        return np.load(path, allow_pickle=False)
    if lower.endswith(".json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        return np.asarray(payload)
    raise ValueError("Embeddings must be provided as .npy or .json")


def _write_bundle(metadata_bytes: bytes, embeddings: np.ndarray, output: Path) -> None:
    metadata_array = np.frombuffer(metadata_bytes, dtype=np.uint8)
    np.savez_compressed(output, embeddings=embeddings, metadata_json=metadata_array)


def _write_hash(bundle_path: Path, explicit_path: Optional[Path]) -> Path:
    target = explicit_path or bundle_path.with_suffix(".sha256")
    digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    target.write_text(f"{digest}  {bundle_path.name}\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True, help="Path to metadata JSON file")
    parser.add_argument("--embeddings", required=True, help="Path to embeddings (.npy or JSON)")
    parser.add_argument("--output", required=True, help="Destination .npz bundle path")
    parser.add_argument(
        "--hash-output",
        help="Optional path for the generated .sha256 file (defaults to bundle name)",
    )
    args = parser.parse_args()

    metadata_path = Path(args.metadata)
    embeddings_path = Path(args.embeddings)
    output_path = Path(args.output)
    hash_output = Path(args.hash_output) if args.hash_output else None

    metadata_bytes = _read_metadata(metadata_path)
    embeddings = _read_embeddings(embeddings_path)
    embeddings = np.asarray(embeddings)
    if embeddings.dtype == object:
        raise ValueError("Embeddings JSON must contain numeric lists; got object dtype")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_bundle(metadata_bytes, embeddings, output_path)
    hash_path = _write_hash(output_path, hash_output)

    print(f"Wrote bundle: {output_path}")
    print(f"SHA256 written to: {hash_path}")


if __name__ == "__main__":
    main()
