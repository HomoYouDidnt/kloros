#!/usr/bin/env python
"""Build a FAISS index for the local accuracy stack."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, List, Tuple

import faiss  # type: ignore
import numpy as np
import sentence_transformers  # type: ignore


def _iter_chunks(path: Path) -> Iterable[Tuple[str, str]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not parts:
        parts = [text]
    _rel = path.stem
    for idx, chunk in enumerate(parts):
        chunk_id = f"{path.name}#p{idx}"
        yield chunk_id, chunk


def build_index(
    corpus_dir: Path,
    output_dir: Path,
    model_path: str | None = None,
    model_name: str = "BAAI/bge-m3",
) -> None:
    corpus_dir = corpus_dir.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    model = sentence_transformers.SentenceTransformer(model_path or model_name)

    chunk_ids: List[str] = []
    chunk_texts: List[str] = []
    for file_path in sorted(corpus_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".md", ".txt"}:
            continue
        for chunk_id, chunk_text in _iter_chunks(file_path):
            chunk_ids.append(chunk_id)
            chunk_texts.append(chunk_text)

    if not chunk_texts:
        raise RuntimeError(f"No corpus files found under {corpus_dir}")

    embeddings = model.encode(chunk_texts, convert_to_numpy=True, normalize_embeddings=True)
    embeddings = np.asarray(embeddings, dtype=np.float32)
    if embeddings.ndim != 2:
        raise RuntimeError("Unexpected embedding shape")

    faiss.normalize_L2(embeddings)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    index_path = output_dir / "index.faiss"
    meta_path = output_dir / "meta.json"
    faiss.write_index(index, str(index_path))

    metadata = [
        {
            "id": chunk_id,
            "text": text,
        }
        for chunk_id, text in zip(chunk_ids, chunk_texts, strict=False)
    ]
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, help="Directory containing raw documents")
    parser.add_argument("--out", required=True, help="Directory where the index will be written")
    parser.add_argument("--model", default="BAAI/bge-m3", help="Model name to download if model-path missing")
    parser.add_argument("--model-path", default=None, help="Optional local model path")
    args = parser.parse_args()

    build_index(Path(args.corpus), Path(args.out), model_path=args.model_path, model_name=args.model)


if __name__ == "__main__":
    main()
