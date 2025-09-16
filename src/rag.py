"""
Lightweight RAG support for KLoROS
- Loads precomputed document metadata and embeddings (npy/pkl/parquet/json/csv)
- Performs cosine similarity retrieval (numpy)
- Builds a context-augmented prompt for an LLM (Ollama compatible)
- Provides a simple wrapper to call Ollama's generate API

Design constraints:
- Minimal dependencies: only numpy + pickle used by default. If parquet is provided, pandas will be used if available.
- Expects precomputed embeddings for documents. For queries you can either provide an embedding or supply an embedder callable.

Usage example (see src/rag_demo.py):
  rag = RAG(metadata_path, embeddings_path)
  resp = rag.answer(
      question_text,
      embedder=my_embedder_callable,   # returns numpy array (D,)
      top_k=5,
      ollama_url='http://localhost:11434/api/generate',
      ollama_model='nous-hermes:13b-q4_0',
  )

"""
from __future__ import annotations

import json
import os
import pickle
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import requests


class RAG:
    def __init__(self, metadata_path: Optional[str] = None, embeddings_path: Optional[str] = None) -> None:
        self.metadata_path = metadata_path
        self.embeddings_path = embeddings_path
        self.metadata: List[Dict[str, Any]] = []
        self.embeddings: Optional[np.ndarray] = None

        if metadata_path:
            self.metadata = self._load_metadata(metadata_path)
        if embeddings_path:
            self.embeddings = self._load_embeddings(embeddings_path)

        if self.embeddings is not None and self.metadata:
            if len(self.metadata) != len(self.embeddings):
                # allow more flexible shapes but warn
                print(f"[RAG] warning: metadata ({len(self.metadata)}) != embeddings ({len(self.embeddings)})")

    # ----------------- loading helpers -----------------
    def _load_embeddings(self, path: str) -> np.ndarray:
        path = os.path.expanduser(path)
        if path.endswith('.npy') or path.endswith('.npz'):
            arr = np.load(path)
            return np.asarray(arr)
        # try pickle
        with open(path, 'rb') as f:
            obj = pickle.load(f)
            if isinstance(obj, np.ndarray):
                return obj
            # some pickles may wrap a dict
            if isinstance(obj, dict) and 'embeddings' in obj:
                return np.asarray(obj['embeddings'])
            # try list/iterable
            return np.asarray(obj)

    def _load_metadata(self, path: str) -> List[Dict[str, Any]]:
        path = os.path.expanduser(path)
        if path.endswith('.parquet'):
            try:
                import pandas as pd

                df = pd.read_parquet(path)
                return df.to_dict(orient='records')
            except Exception as e:
                raise RuntimeError("Failed to load parquet metadata: " + str(e))
        if path.endswith('.json') or path.endswith('.ndjson'):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        if path.endswith('.csv'):
            try:
                import csv

                rows: List[Dict[str, Any]] = []
                with open(path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        rows.append(dict(r))
                return rows
            except Exception as e:
                raise RuntimeError("Failed to load csv metadata: " + str(e))
        # try pickle
        with open(path, 'rb') as f:
            obj = pickle.load(f)
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict) and 'metadata' in obj:
                return obj['metadata']
            raise RuntimeError("Unknown metadata format in pickle")

    # ----------------- math -----------------
    @staticmethod
    def _cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        # query: (D,), matrix: (N,D)
        if query.ndim != 1:
            query = query.reshape(-1)
        qn = np.linalg.norm(query) + 1e-12
        mn = np.linalg.norm(matrix, axis=1) + 1e-12
        sims = (matrix @ query) / (mn * qn)
        return sims

    # ----------------- retrieval -----------------
    def retrieve_by_embedding(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        if self.embeddings is None:
            raise RuntimeError("No document embeddings loaded")
        sims = self._cosine_similarity(query_embedding, self.embeddings)
        idx = np.argsort(-sims)[:top_k]
        results = []
        for i in idx:
            meta = self.metadata[i] if i < len(self.metadata) else {"id": int(i)}
            results.append((meta, float(sims[i])))
        return results

    def retrieve_by_text(self, query_text: str, embedder: Callable[[str], np.ndarray], top_k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        query_emb = embedder(query_text)
        return self.retrieve_by_embedding(query_emb, top_k=top_k)

    # ----------------- prompt building and LLM call -----------------
    def build_prompt(self, question: str, retrieved: Iterable[Tuple[Dict[str, Any], float]], max_ctx_chars: int = 3000) -> str:
        # Create a compact context block from retrieved documents
        parts: List[str] = []
        used = 0
        for meta, score in retrieved:
            text = ''
            # common fields: 'quote', 'transcript', 'text'
            for k in ('quote', 'transcript', 'text', 'caption'):
                if k in meta and meta[k]:
                    text = str(meta[k])
                    break
            if not text and 'file' in meta:
                text = f"(audio file: {meta.get('file')})"
            block = f"[score={score:.3f}] {text}"
            if used + len(block) > max_ctx_chars:
                break
            parts.append(block)
            used += len(block)
        context = "\n\n".join(parts)
        prompt = (
            "You are KLoROS, a concise assistant. Use the following audio-derived quotes and context to answer the user's question.\n\n"
            + "Context:\n" + context
            + "\n\nQuestion:\n" + question
            + "\n\nAnswer concisely (1-2 short sentences):"
        )
        return prompt

    def generate_with_ollama(self, prompt: str, ollama_url: str = "http://localhost:11434/api/generate", model: str = "nous-hermes:13b-q4_0") -> str:
        payload = {"model": model, "prompt": prompt, "stream": False}
        try:
            r = requests.post(ollama_url, json=payload, timeout=60)
            if r.status_code == 200:
                return r.json().get('response', '').strip()
            else:
                return f"Ollama error: HTTP {r.status_code}"
        except requests.RequestException as e:
            return f"Ollama request failed: {e}"

    def answer(self, question: str, embedder: Optional[Callable[[str], np.ndarray]] = None, query_embedding: Optional[np.ndarray] = None, top_k: int = 5, ollama_url: str = "http://localhost:11434/api/generate", model: str = "nous-hermes:13b-q4_0") -> Dict[str, Any]:
        if query_embedding is None and embedder is None:
            raise ValueError("Provide either query_embedding or an embedder callable")
        if query_embedding is None:
            query_embedding = embedder(question)
        retrieved = self.retrieve_by_embedding(query_embedding, top_k=top_k)
        prompt = self.build_prompt(question, retrieved)
        response = self.generate_with_ollama(prompt, ollama_url=ollama_url, model=model)
        return {"response": response, "prompt": prompt, "retrieved": retrieved}


# end
