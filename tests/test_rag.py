import os
import shutil
from pathlib import Path

import numpy as np
import pytest

from src.rag import RAG


def dummy_embedder(text: str) -> np.ndarray:
    # Simple deterministic embedder: sum of char codes modulo 100 mapped into a 384-d vector
    s = sum(ord(c) for c in text) % 100
    v = np.zeros(384, dtype=np.float32)
    v[0] = float(s) / 100.0
    return v


def test_rag_retrieval_and_prompt(tmp_path, monkeypatch):
    # Use rag_data in repo root
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    bundle = os.path.join(repo_root, "rag_data", "rag_store.npz")
    hash_path = os.path.join(repo_root, "rag_data", "rag_store.sha256")

    assert os.path.exists(bundle), "rag_data/rag_store.npz missing"
    assert os.path.exists(hash_path), "rag_data/rag_store.sha256 missing"

    r = RAG(bundle_path=bundle)

    # Monkeypatch requests.post used by generate_with_ollama to avoid network calls
    class DummyResp:
        status_code = 200

        def json(self):
            return {"response": "Dummy Ollama response"}

    def fake_post(_url, json, timeout=None):
        # ensure prompt was constructed
        assert "prompt" in json
        _ = timeout
        return DummyResp()

    monkeypatch.setattr("requests.post", fake_post)

    out = r.answer(
        "What is KLoROS?",
        embedder=dummy_embedder,
        top_k=3,
        ollama_url="http://localhost:11434/api/generate",
        model="nous-hermes:13b-q4_0",
    )
    assert "response" in out
    assert out["response"] == "Dummy Ollama response"


def test_rag_hash_mismatch(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent
    bundle = repo_root / "rag_data" / "rag_store.npz"
    hash_path = bundle.with_suffix(".sha256")

    tmp_bundle = tmp_path / "rag_store.npz"
    tmp_hash = tmp_path / "rag_store.sha256"
    shutil.copyfile(bundle, tmp_bundle)
    shutil.copyfile(hash_path, tmp_hash)

    data = bytearray(tmp_bundle.read_bytes())
    data[0] ^= 0x01
    tmp_bundle.write_bytes(data)

    with pytest.raises(ValueError):
        RAG(bundle_path=str(tmp_bundle))
