"""Simple demo for RAG module

This demo assumes you have:
- precomputed document embeddings in a .npy or .pkl file
- metadata in JSON/CSV/Pickle/parquet
- an embedder callable (or you can pass a precomputed query embedding)

Run the demo like:
    python -m src.rag_demo

The demo will print the Ollama response and the retrieval context.
"""
from __future__ import annotations

import os
import sys
import numpy as np

# Ensure repo root is on sys.path when executed as a script (helps import during tooling/tests)
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.rag import RAG


def dummy_embedder(text: str) -> np.ndarray:
    # dummy (random) embedding for demonstration — replace with your real embedder
    rng = np.random.RandomState(abs(hash(text)) % (2**32))
    return rng.normal(size=(768,))


def main():
    # adjust paths to your data
    metadata_path = os.getenv('RAG_METADATA') or 'configs/rag_metadata.json'
    embeddings_path = os.getenv('RAG_EMBEDDINGS') or 'configs/rag_embeddings.npy'

    rag = RAG(metadata_path=metadata_path, embeddings_path=embeddings_path)
    question = "Give a short line in the voice of KLoROS about patience."

    out = rag.answer(question, embedder=dummy_embedder, top_k=5)
    print('Prompt:')
    print(out['prompt'][:2000])
    print('\nResponse:')
    print(out['response'])


if __name__ == '__main__':
    main()
