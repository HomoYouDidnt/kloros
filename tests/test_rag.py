import numpy as np
import os
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
    metadata = os.path.join(repo_root, "rag_data", "metadata.json")
    embeddings = os.path.join(repo_root, "rag_data", "embeddings.npy")

    assert os.path.exists(metadata), "rag_data/metadata.json missing"
    assert os.path.exists(embeddings), "rag_data/embeddings.npy missing"

    r = RAG(metadata_path=metadata, embeddings_path=embeddings)

    # Monkeypatch requests.post used by generate_with_ollama to avoid network calls
    class DummyResp:
        status_code = 200

        def json(self):
            return {"response": "Dummy Ollama response"}


    def fake_post(url, json, timeout=None):
        # ensure prompt was constructed
        assert "prompt" in json
        return DummyResp()

    monkeypatch.setattr("requests.post", fake_post)

    out = r.answer("What is KLoROS?", embedder=dummy_embedder, top_k=3, ollama_url="http://localhost:11434/api/generate", model="nous-hermes:13b-q4_0")
    assert "response" in out
    assert out["response"] == "Dummy Ollama response"
