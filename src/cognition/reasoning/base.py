# src/reasoning/base.py
from __future__ import annotations
import os
import requests
from typing import List, Dict, Any

# ---- Result types ----

class ReasoningResult:
    """Result from a reasoning backend."""

    def __init__(self, reply_text: str, sources: List[str] = None, meta: Dict[str, Any] = None):
        self.reply_text = reply_text
        self.sources = sources if sources is not None else []
        self.meta = meta

    def __eq__(self, other):
        if not isinstance(other, ReasoningResult):
            return False
        return (self.reply_text == other.reply_text and
                self.sources == other.sources and
                self.meta == other.meta)

# ---- Minimal adapters ----

class MockReasoner:
    def generate(self, text: str) -> str:
        return "ok"

    def reply(self, text: str, kloros_instance=None, **kwargs) -> ReasoningResult:
        return ReasoningResult("ok", sources=["mock"])

class OllamaReasoner:
    def __init__(self, base_url: str, model: str, system_prompt: str, temperature: float = 0.6, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.timeout = timeout
        print(f"[reasoning] Initialized ollama backend: {base_url} model={model}")

    def generate(self, text: str) -> str:
        from src.core.config.models_config import get_ollama_context_size

        r = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": text,
                "system": self.system_prompt,
                "options": {
                    "temperature": self.temperature,
                    "num_gpu": 999,
                    "main_gpu": 0,
                    "num_ctx": get_ollama_context_size(check_vram=False)  # Centralized config
                },
                "stream": False,
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        return (r.json().get("response") or "").strip()
    
    def reply(self, text: str, kloros_instance=None, **kwargs) -> ReasoningResult:
        import json

        enable_streaming = kwargs.get("enable_streaming", True)

        if not enable_streaming or kloros_instance is None:
            response = self.generate(text)
            return ReasoningResult(response)

        buffer = ""
        complete_response = ""
        sentence_endings = {'.', '!', '?'}

        try:
            r = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": text,
                    "system": self.system_prompt,
                    "options": {
                        "temperature": self.temperature,
                        "num_gpu": 999,
                        "main_gpu": 0,
                        "num_ctx": get_ollama_context_size(check_vram=False)
                    },
                    "stream": True,
                },
                stream=True,
                timeout=self.timeout,
            )

            if r.status_code != 200:
                return ReasoningResult(f"Error: Ollama HTTP {r.status_code}")

            for line in r.iter_lines():
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    buffer += token
                    complete_response += token

                    if token.strip() and token.strip()[-1] in sentence_endings:
                        sentence = buffer.strip()
                        if len(sentence) > 20 and hasattr(kloros_instance, 'speak'):
                            kloros_instance.speak(sentence)
                            buffer = ""

                    if chunk.get("done", False):
                        break

                except json.JSONDecodeError:
                    continue

            if buffer.strip() and hasattr(kloros_instance, 'speak'):
                kloros_instance.speak(buffer.strip())

            return ReasoningResult(complete_response.strip())

        except requests.RequestException as e:
            return ReasoningResult(f"Ollama error: {e}")

# ---- Factory ----

def create_reasoning_backend(name: str, **kwargs):
    """
    Create the requested reasoning backend, or raise ValueError for unknown.
    Recognized: 'mock', 'ollama', 'llama', 'qa'

    Note: 'rag' is deprecated - use MetaAgentKLoROS via UMN for voice,
    or 'ollama' for programmatic reasoning.

    Args:
        name: Backend name to create
        **kwargs: Additional parameters to pass to backend constructor
    """
    b = (name or "mock").lower()

    if b in ("mock", "none", "disabled"):
        from .mock_backend import MockReasoningBackend
        return MockReasoningBackend(**kwargs)

    if b in ("ollama", "llm", "local"):
        from src.core.config.models_config import get_ollama_url, get_ollama_model
        host = os.getenv("OLLAMA_HOST", get_ollama_url())
        model = get_ollama_model()

        # Connect to persona system
        try:
            from src.governance.persona.kloros import PERSONA_PROMPT
            prompt = PERSONA_PROMPT.strip()
            print(f"[reasoning] Using KLoROS persona system")
        except ImportError:
            # Fallback to environment or default
            # Import authentic KLoROS persona instead of generic override
            try:
                from src.governance.persona.kloros import PERSONA_PROMPT
                prompt = PERSONA_PROMPT
            except ImportError:
                prompt = os.getenv("LLM_SYSTEM_PROMPT", "")
            print(f"[reasoning] Using fallback prompt")

        return OllamaReasoner(base_url=host, model=model, system_prompt=prompt)

    if b in ("llama", "llama.cpp", "llamacpp"):
        from .llama_adapter import LlamaAdapter
        from src.core.config.models_config import get_llama_url_for_mode

        mode = kwargs.get("mode", "live")
        url = get_llama_url_for_mode(mode)

        try:
            from src.governance.persona.kloros import PERSONA_PROMPT
            prompt = PERSONA_PROMPT.strip()
            print(f"[reasoning] Using KLoROS persona for llama.cpp")
        except ImportError:
            prompt = os.getenv("LLM_SYSTEM_PROMPT", "")
            print(f"[reasoning] Using fallback prompt for llama.cpp")

        print(f"[reasoning] Initialized llama.cpp backend: {url} mode={mode}")
        return LlamaAdapter(base_url=url, model=None, system_prompt=prompt)

    if b in ("rag",):
        import warnings
        warnings.warn(
            "The 'rag' backend is deprecated. For voice input, use MetaAgentKLoROS via UMN. "
            "For programmatic reasoning, use 'ollama' backend. Falling back to 'ollama'.",
            DeprecationWarning,
            stacklevel=2
        )
        from src.core.config.models_config import get_ollama_url, get_ollama_model
        host = os.getenv("OLLAMA_HOST", get_ollama_url())
        model = get_ollama_model()
        try:
            from src.governance.persona.kloros import PERSONA_PROMPT
            prompt = PERSONA_PROMPT.strip()
        except ImportError:
            prompt = os.getenv("LLM_SYSTEM_PROMPT", "")
        print(f"[reasoning] RAG backend deprecated, using OllamaReasoner fallback")
        return OllamaReasoner(base_url=host, model=model, system_prompt=prompt)

    if b in ("qa",):
        from .local_qa_backend import LocalQaBackend
        print(f"[reasoning] Initialized QA backend")
        return LocalQaBackend(**kwargs)

    # Preserve existing test behavior for unknown backends
    raise ValueError(f"Unknown reasoning backend: {b}")
