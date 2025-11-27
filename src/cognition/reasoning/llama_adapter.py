import requests
import json
import logging
from typing import Optional, Generator

logger = logging.getLogger(__name__)


class LlamaAdapter:
    """
    Adapts Ollama-style requests to llama.cpp server format.
    Provides drop-in replacement for OllamaReasoner with same interface.
    """

    def __init__(
        self,
        base_url: str,
        model: str = None,
        system_prompt: str = "",
        temperature: float = 0.6,
        timeout: int = 120
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.timeout = timeout
        logger.info(f"[llama_adapter] Initialized: {base_url} (model={model})")

    def _build_prompt(self, text: str, system: Optional[str] = None) -> str:
        sys = system if system is not None else self.system_prompt
        if sys:
            return f"{sys}\n\nUser: {text}\n\nAssistant:"
        else:
            return text

    def generate(self, text: str, **kwargs) -> str:
        """Generate completion using llama.cpp /completion endpoint."""
        system = kwargs.get("system", None)
        prompt = self._build_prompt(text, system)

        payload = {
            "prompt": prompt,
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", 0.95),
            "repeat_penalty": kwargs.get("repeat_penalty", 1.1),
            "n_predict": kwargs.get("num_predict", -1),
            "stream": kwargs.get("stream", False),
            "stop": kwargs.get("stop", []),
        }

        if kwargs.get("stream"):
            return self._stream_completion(payload, kwargs.get("timeout", self.timeout))

        try:
            r = requests.post(
                f"{self.base_url}/completion",
                json=payload,
                timeout=kwargs.get("timeout", self.timeout)
            )
            r.raise_for_status()
            response = r.json()
            content = response.get("content", "").strip()
            logger.debug(f"[llama_adapter] Generated {len(content)} chars")
            return content
        except requests.RequestException as e:
            logger.error(f"[llama_adapter] Request failed: {e}")
            raise

    def _stream_completion(self, payload: dict, timeout: int) -> str:
        """Handle streaming completion."""
        try:
            r = requests.post(
                f"{self.base_url}/completion",
                json=payload,
                stream=True,
                timeout=timeout
            )
            r.raise_for_status()

            complete = ""
            for line in r.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("content", "")
                        complete += token
                        if chunk.get("stop", False):
                            break
                    except json.JSONDecodeError:
                        logger.warning(f"[llama_adapter] Invalid JSON in stream: {line}")
                        continue
            return complete.strip()
        except requests.RequestException as e:
            logger.error(f"[llama_adapter] Streaming failed: {e}")
            raise

    def reply(self, text: str, kloros_instance=None, **kwargs):
        """Generate reply with optional streaming to TTS."""
        from src.cognition.reasoning.base import ReasoningResult

        enable_streaming = kwargs.get("enable_streaming", True)

        if not enable_streaming or kloros_instance is None:
            response = self.generate(text, **kwargs)
            return ReasoningResult(response)

        sys = kwargs.get("system", None)
        prompt = self._build_prompt(text, sys)

        payload = {
            "prompt": prompt,
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", 0.95),
            "repeat_penalty": kwargs.get("repeat_penalty", 1.1),
            "n_predict": kwargs.get("num_predict", -1),
            "stream": True,
            "stop": kwargs.get("stop", []),
        }

        buffer = ""
        complete_response = ""
        sentence_endings = {'.', '!', '?'}

        try:
            r = requests.post(
                f"{self.base_url}/completion",
                json=payload,
                stream=True,
                timeout=self.timeout
            )

            if r.status_code != 200:
                return ReasoningResult(f"Error: llama.cpp HTTP {r.status_code}")

            for line in r.iter_lines():
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                    token = chunk.get("content", "")
                    buffer += token
                    complete_response += token

                    if token.strip() and token.strip()[-1] in sentence_endings:
                        sentence = buffer.strip()
                        if len(sentence) > 20 and hasattr(kloros_instance, 'speak'):
                            kloros_instance.speak(sentence)
                            buffer = ""

                    if chunk.get("stop", False):
                        break
                except json.JSONDecodeError:
                    continue

            if buffer.strip() and hasattr(kloros_instance, 'speak'):
                kloros_instance.speak(buffer.strip())

            return ReasoningResult(complete_response.strip())
        except requests.RequestException as e:
            return ReasoningResult(f"llama.cpp error: {e}")

    def health_check(self) -> bool:
        """Check if llama-server is healthy."""
        try:
            r = requests.get(f"{self.base_url}/health", timeout=2)
            if r.status_code == 200:
                status = r.json().get("status", "")
                return status == "ok"
        except Exception:
            pass
        return False
