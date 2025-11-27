"""
Lightweight RAG support for KLoROS
- Loads precomputed document metadata and embeddings (npy/npz/json/parquet/csv)
- Performs cosine similarity retrieval (numpy)
- Builds a context-augmented prompt for an LLM (Ollama compatible)
- Provides a simple wrapper to call Ollama's generate API

Design constraints:
- Minimal dependencies: only numpy + standard data formats by default. If parquet is provided, pandas will be used if available.
- Expects precomputed embeddings for documents. For queries you can either provide an embedding or supply an embedder callable.

Usage example (see src/rag_demo.py):
  rag = RAG(bundle_path="rag_data/rag_store.npz")
  resp = rag.answer(
      question_text,
      embedder=my_embedder_callable,   # returns numpy array (D,)
      top_k=5,
      # ollama_url and model default to SSOT config if not provided
  )

"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import requests  # type: ignore

from src.cognition.logic.kloros import log_event


class RAG:
    def __init__(
        self,
        metadata_path: Optional[str] = None,
        embeddings_path: Optional[str] = None,
        bundle_path: Optional[str] = None,
        verify_bundle_hash: bool = True,
    ) -> None:
        """Create a RAG helper.

        Args:
            metadata_path: Path to metadata (JSON/CSV/Parquet) or an .npz bundle.
            embeddings_path: Path to embeddings (npy/npz/json).
            bundle_path: Optional explicit path to an .npz bundle containing both.
            verify_bundle_hash: When loading an .npz bundle, enforce SHA256 verification.
        """

        self.metadata_path = metadata_path
        self.embeddings_path = embeddings_path
        self.bundle_path = bundle_path
        self.verify_bundle_hash = verify_bundle_hash
        self.metadata: List[Dict[str, Any]] = []
        self.embeddings: Optional[np.ndarray] = None
        # Optional runtime Faiss index (set when available)
        self.faiss_index: Optional[Any] = None

        bundle_candidate = bundle_path or self._detect_bundle(metadata_path, embeddings_path)
        if bundle_candidate:
            self.bundle_path = bundle_candidate
            self.metadata_path = bundle_candidate
            self.embeddings_path = bundle_candidate
            self.metadata, self.embeddings = self._load_bundle(bundle_candidate, verify_bundle_hash)
        else:
            if metadata_path:
                self.metadata = self._load_metadata(metadata_path)
            if embeddings_path:
                self.embeddings = self._load_embeddings(embeddings_path)

        doc_count = len(self.metadata)
        embed_rows = int(self.embeddings.shape[0]) if self.embeddings is not None else 0
        log_event(
            "rag_init",
            docs=doc_count,
            embeddings=embed_rows,
            from_bundle=bool(self.bundle_path),
        )
        if doc_count and embed_rows and doc_count != embed_rows:
            log_event(
                "rag_mismatch",
                docs=doc_count,
                embeddings=embed_rows,
            )
            print(f"[RAG] warning: metadata ({doc_count}) != embeddings ({embed_rows})")

    @staticmethod
    def _detect_bundle(
        metadata_path: Optional[str], embeddings_path: Optional[str]
    ) -> Optional[str]:
        for candidate in (metadata_path, embeddings_path):
            if candidate and candidate.lower().endswith(".npz"):
                return candidate
        return None

    def _load_bundle(self, path: str, verify_hash: bool) -> Tuple[List[Dict[str, Any]], np.ndarray]:
        bundle_path = Path(os.path.expanduser(path))
        if verify_hash:
            self._verify_bundle_hash(bundle_path)
        with np.load(bundle_path, allow_pickle=True) as data:
            if "embeddings" not in data.files or "metadata_json" not in data.files:
                raise ValueError(
                    f"Bundle {bundle_path} must contain 'embeddings' and 'metadata_json' entries"
                )
            embeddings = self._validate_embedding_array(data["embeddings"], str(bundle_path))
            metadata_bytes = np.asarray(data["metadata_json"], dtype=np.uint8).tobytes()
        metadata = json.loads(metadata_bytes.decode("utf-8"))
        metadata_list = self._validate_metadata(metadata, str(bundle_path))
        log_event(
            "rag_bundle_loaded",
            path=str(bundle_path),
            docs=len(metadata_list),
            embeddings=int(embeddings.shape[0]),
            verified=bool(verify_hash),
        )
        return metadata_list, embeddings

    def _verify_bundle_hash(self, bundle_path: Path) -> None:
        hash_path = bundle_path.with_suffix(".sha256")
        if not hash_path.exists():
            raise FileNotFoundError(f"Missing hash file for bundle: {hash_path}")
        expected_line = hash_path.read_text(encoding="utf-8").strip()
        if not expected_line:
            raise ValueError(f"Hash file {hash_path} is empty")
        expected_hash = expected_line.split()[0]
        actual_hash = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(
                f"Hash mismatch for bundle {bundle_path}: expected {expected_hash}, got {actual_hash}"
            )

    # ----------------- loading helpers -----------------
    def _load_embeddings(self, path: str) -> np.ndarray:
        normalized_path = os.path.expanduser(path)
        lower_path = normalized_path.lower()

        if lower_path.endswith(".npy"):
            data = np.load(normalized_path, allow_pickle=False)
        elif lower_path.endswith(".npz"):
            with np.load(normalized_path, allow_pickle=False) as data:
                if "embeddings" in data.files:
                    candidate = data["embeddings"]
                elif len(data.files) == 1:
                    candidate = data[data.files[0]]
                else:
                    raise ValueError(
                        "NPZ embeddings must contain an 'embeddings' array or a single unnamed array"
                    )
            data = candidate
        elif lower_path.endswith(".json") or lower_path.endswith(".ndjson"):
            with open(normalized_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            data = payload
        else:
            raise ValueError(
                "Unsupported embeddings file type. Expected .npy/.npz/.json/.ndjson. "
                "Pickle-based formats are not allowed."
            )

        arr = self._validate_embedding_array(data, normalized_path)
        rows = int(arr.shape[0]) if arr.ndim >= 1 else len(arr)
        dims = int(arr.shape[1]) if arr.ndim >= 2 else 0
        log_event("rag_embeddings_loaded", path=normalized_path, rows=rows, dims=dims)
        return arr

    def _load_metadata(self, path: str) -> List[Dict[str, Any]]:
        normalized_path = os.path.expanduser(path)
        if normalized_path.endswith(".parquet"):
            try:
                import pandas as pd  # type: ignore

                df = pd.read_parquet(normalized_path)
                payload: Any = df.to_dict(orient="records")
            except Exception as e:
                raise RuntimeError("Failed to load parquet metadata: " + str(e)) from e
        elif normalized_path.endswith(".json") or normalized_path.endswith(".ndjson"):
            with open(normalized_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        elif normalized_path.endswith(".csv"):
            try:
                import csv

                rows: List[Dict[str, Any]] = []
                with open(normalized_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        rows.append(dict(r))
                payload = rows
            except Exception as e:
                raise RuntimeError("Failed to load csv metadata: " + str(e)) from e
        else:
            raise ValueError("Unsupported metadata file type. Expected .json/.ndjson/.csv/.parquet")

        metadata = self._validate_metadata(payload, normalized_path)
        log_event("rag_metadata_loaded", path=normalized_path, docs=len(metadata))
        return metadata

    @staticmethod
    def _validate_metadata(payload: Any, source: str) -> List[Dict[str, Any]]:
        if not isinstance(payload, list):
            raise ValueError(f"Metadata in {source} must be a list of objects")
        validated: List[Dict[str, Any]] = []
        for idx, item in enumerate(payload):
            if not isinstance(item, dict):
                raise ValueError(f"Metadata entry {idx} in {source} is not a mapping")
            validated.append(item)
        return validated

    @staticmethod
    def _validate_embedding_array(payload: Any, source: str) -> np.ndarray:
        """Validate and convert embeddings to numpy array."""
        if not isinstance(payload, np.ndarray):
            try:
                arr = np.asarray(payload, dtype=np.float32)
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Could not convert embeddings in {source} to numpy array: {e}"
                ) from e
        else:
            arr = payload.astype(np.float32)

        if arr.ndim not in (1, 2):
            raise ValueError(f"Embeddings in {source} must be 1D or 2D array, got {arr.ndim}D")

        if arr.ndim == 1:
            # Single embedding vector, reshape to (1, D)
            arr = arr.reshape(1, -1)

        if arr.shape[0] == 0:
            raise ValueError(f"Embeddings in {source} cannot be empty")

        if arr.shape[1] == 0:
            raise ValueError(f"Embedding dimension in {source} cannot be zero")

        return arr

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
    def retrieve_by_embedding(
        self, query_embedding: np.ndarray, top_k: int = 5
    ) -> List[Tuple[Dict[str, Any], float]]:
        if self.embeddings is None:
            raise RuntimeError("No document embeddings loaded")
        sims = self._cosine_similarity(query_embedding, self.embeddings)
        idx = np.argsort(-sims)[:top_k]
        results = []
        for i in idx:
            meta = self.metadata[i] if i < len(self.metadata) else {"id": int(i)}
            results.append((meta, float(sims[i])))
        log_event(
            "rag_retrieve",
            top_k=top_k,
            returned=len(results),
            docs_available=int(self.embeddings.shape[0]),
        )
        return results

    def retrieve_by_text(
        self, query_text: str, embedder: Callable[[str], np.ndarray], top_k: int = 5
    ) -> List[Tuple[Dict[str, Any], float]]:
        query_emb = embedder(query_text)
        return self.retrieve_by_embedding(query_emb, top_k=top_k)

    # ----------------- prompt building and LLM call -----------------
    def build_prompt(
        self,
        question: str,
        retrieved: Iterable[Tuple[Dict[str, Any], float]],
        max_ctx_chars: int = 12000,
        tool_descriptions: str = "",
        additional_context: str = "",
    ) -> str:
        parts: List[str] = []
        used = 0
        for meta, score in retrieved:
            text = ""
            for k in ("quote", "transcript", "text", "caption"):
                if k in meta and meta[k]:
                    text = str(meta[k])
                    break
            if not text and "file" in meta:
                text = f"(audio file: {meta.get('file')})"
            block = f"[score={score:.3f}] {text}"
            if used + len(block) > max_ctx_chars:
                break
            parts.append(block)
            used += len(block)
        context = "\n\n".join(parts)

        prompt_parts = []
        prompt_parts.append("Use the following audio-derived quotes and context to answer the user's question.\n")

        if tool_descriptions:
            prompt_parts.append(tool_descriptions)
            prompt_parts.append("\n")

        if additional_context:
            prompt_parts.append(additional_context)
            prompt_parts.append("\n")

        prompt_parts.append("Context:\n")
        prompt_parts.append(context)
        prompt_parts.append("\n\nQuestion:\n")
        prompt_parts.append(question)
        prompt_parts.append("\n\nAnswer concisely (1-2 short sentences):")

        return "".join(prompt_parts)

    def generate_with_ollama(
        self,
        prompt: str,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None,
        stream_callback=None,
    ) -> str:
        """Generate response from Ollama with optional streaming.

        Args:
            prompt: The prompt to send to Ollama
            ollama_url: Ollama API endpoint (defaults to SSOT config)
            model: Model name to use (defaults to SSOT config)
            stream_callback: Optional callback function(chunk: str) called for each token

        Returns:
            Complete response text
        """
        # Get defaults from SSOT config
        if ollama_url is None:
            from src.core.config.models_config import get_ollama_url
            ollama_url = get_ollama_url() + "/api/generate"
        if model is None:
            from src.core.config.models_config import get_ollama_model
            model = get_ollama_model()
        # Import KLoROS persona
        try:
            from src.governance.persona.kloros import PERSONA_PROMPT
            system_prompt = PERSONA_PROMPT.strip()
        except ImportError:
            # Fallback should never override KLoROS personality - use minimal prompt
            system_prompt = ""

        # Enable streaming if callback provided
        use_streaming = stream_callback is not None

        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": use_streaming,
            "options": {"num_gpu": 999, "main_gpu": 0}
        }
        print(f"[DEBUG] Ollama API: {ollama_url}")
        print(f"[DEBUG] Prompt preview (first 800 chars):\n{prompt[:800]}\n...")
        log_event("rag_generate_request", model=model, url=ollama_url, streaming=use_streaming)

        try:
            if use_streaming:
                # Streaming mode with callback
                import json
                complete_response = ""
                buffer = ""
                sentence_endings = {'.', '!', '?'}

                r = requests.post(ollama_url, json=payload, stream=True, timeout=60)
                if r.status_code != 200:
                    msg = f"Ollama error: HTTP {r.status_code}"
                    log_event("rag_generate_response", model=model, status="http_error", code=int(r.status_code))
                    return msg

                for line in r.iter_lines():
                    if not line:
                        continue

                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        buffer += token
                        complete_response += token

                        # Check for sentence boundary
                        if token.strip() and token.strip()[-1] in sentence_endings:
                            sentence = buffer.strip()
                            if len(sentence) > 20:  # Only send substantial sentences
                                stream_callback(sentence)
                                buffer = ""

                        if chunk.get("done", False):
                            break

                    except json.JSONDecodeError as e:
                        print(f"[RAG] JSON decode error: {e}")
                        continue

                # Send any remaining buffer
                if buffer.strip():
                    stream_callback(buffer.strip())

                response = complete_response.strip()
                log_event("rag_generate_response", model=model, status="ok", length=len(response), streaming=True)
                return response

            else:
                # Non-streaming mode (original behavior)
                r = requests.post(ollama_url, json=payload, timeout=60)
                if r.status_code == 200:
                    response = r.json().get("response", "").strip()
                    log_event("rag_generate_response", model=model, status="ok", length=len(response))
                    return response
                msg = f"Ollama error: HTTP {r.status_code}"
                log_event(
                    "rag_generate_response", model=model, status="http_error", code=int(r.status_code)
                )
                return msg

        except requests.RequestException as e:
            log_event("rag_generate_response", model=model, status="exception", error=str(e))
            return f"Ollama request failed: {e}"

    def generate_with_ollama_chat(
        self,
        prompt: str,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Generate response using Ollama chat API with optional tool support.

        Args:
            prompt: The user prompt/question
            ollama_url: Ollama chat API endpoint (defaults to SSOT config + /api/chat)
            model: Model name to use (defaults to SSOT config)
            tools: Optional list of tool definitions in Ollama format

        Returns:
            Dict with 'response' (str), 'tool_calls' (list), 'done' (bool)
        """
        # Get defaults from SSOT config
        if ollama_url is None:
            from src.core.config.models_config import get_ollama_url
            ollama_url = get_ollama_url() + "/api/chat"
        if model is None:
            from src.core.config.models_config import get_ollama_model
            model = get_ollama_model()

        # Import KLoROS persona
        try:
            from src.governance.persona.kloros import PERSONA_PROMPT
            system_prompt = PERSONA_PROMPT.strip()
        except ImportError:
            system_prompt = ""

        # Build chat API payload
        messages = [{"role": "user", "content": prompt}]
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"num_gpu": 999, "main_gpu": 0}
        }

        # Add system prompt if available
        if system_prompt:
            payload["messages"].insert(0, {"role": "system", "content": system_prompt})

        # Add tools if provided
        if tools:
            payload["tools"] = tools
            print(f"[chat_api] Passing {len(tools)} tools to /api/chat")

        print(f"[chat_api] Using {ollama_url}")
        log_event("rag_chat_request", model=model, url=ollama_url, tools_count=len(tools) if tools else 0)

        try:
            r = requests.post(ollama_url, json=payload, timeout=60)
            if r.status_code == 200:
                result = r.json()
                message = result.get("message", {})
                content = message.get("content", "").strip()
                tool_calls = message.get("tool_calls", [])

                log_event("rag_chat_response", model=model, status="ok", length=len(content), tool_calls=len(tool_calls))
                print(f"[chat_api] Response length: {len(content)}, tool_calls: {len(tool_calls)}")

                return {
                    "response": content,
                    "tool_calls": tool_calls,
                    "done": result.get("done", True)
                }
            else:
                msg = f"Ollama chat API error: HTTP {r.status_code}"
                log_event("rag_chat_response", model=model, status="http_error", code=int(r.status_code))
                return {"response": msg, "tool_calls": [], "done": True}

        except requests.RequestException as e:
            log_event("rag_chat_response", model=model, status="exception", error=str(e))
            return {"response": f"Ollama chat request failed: {e}", "tool_calls": [], "done": True}

    def answer(
        self,
        question: str,
        embedder: Optional[Callable[[str], np.ndarray]] = None,
        query_embedding: Optional[np.ndarray] = None,
        top_k: int = 5,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None,
        stream_callback=None,
        tool_descriptions: str = "",
        additional_context: str = "",
    ) -> Dict[str, Any]:
        # Get defaults from SSOT config
        if ollama_url is None:
            from src.core.config.models_config import get_ollama_url
            ollama_url = get_ollama_url() + "/api/generate"
        if model is None:
            from src.core.config.models_config import get_ollama_model
            model = get_ollama_model()

        if query_embedding is None and embedder is None:
            raise ValueError("Provide either query_embedding or an embedder callable")
        if query_embedding is None:
            if embedder is None:
                raise ValueError("Embedder callable required when query_embedding is absent")
            query_embedding = embedder(question)
        fingerprint = hashlib.sha256(question.encode("utf-8")).hexdigest()[:12]
        log_event(
            "rag_answer",
            question=fingerprint,
            top_k=top_k,
            embedder_supplied=bool(embedder),
            query_supplied=query_embedding is not None,
        )
        retrieved = self.retrieve_by_embedding(query_embedding, top_k=top_k)
        log_event("rag_retrieved_docs", question=fingerprint, count=len(retrieved))
        prompt = self.build_prompt(question, retrieved, tool_descriptions=tool_descriptions, additional_context=additional_context)
        response = self.generate_with_ollama(prompt, ollama_url=ollama_url, model=model, stream_callback=stream_callback)
        status = "ok" if response and not response.lower().startswith("ollama error") else "error"
        log_event(
            "rag_answer_complete",
            question=fingerprint,
            status=status,
            length=len(response),
        )
        return {"response": response, "prompt": prompt, "retrieved": retrieved}


# end
