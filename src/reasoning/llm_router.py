"""
LLM Router - Single Source of Truth for all LLM routing decisions.

This module provides centralized routing for all LLM requests in KLoROS.
It handles:
- Remote vs local LLM selection
- Model selection based on mode (live/think/deep/code)
- Fallback logic
- Service health checking
- Logging and observability

Hybrid GPU Architecture (VRAM optimized):
- ollama-live (GPU 0, port 11434): Qwen2.5 32B instruct (32k context)
  → Handles: LIVE, THINK, DEEP modes
- ollama-think (GPU 1, port 11435): Qwen2.5 32B instruct (32k context)
  → Handles: CODE mode
- Remote LLM via dashboard proxy: Large models (qwen2.5:72b, etc.)

Memory savings: ~15GB RAM (consolidated from 4 CPU Ollama instances)
"""

import logging
import time
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class LLMMode(Enum):
    """Available LLM modes."""
    LIVE = "live"
    THINK = "think"
    DEEP = "deep"
    CODE = "code"


@dataclass
class LLMService:
    """Configuration for an LLM service."""
    name: str
    port: int
    model: str
    description: str
    url: str = None

    def __post_init__(self):
        if self.url is None:
            self.url = f"http://127.0.0.1:{self.port}"


class LLMRouter:
    """
    Single Source of Truth for all LLM routing decisions.

    This router knows about all available LLM services and automatically
    routes requests to the appropriate service based on mode.
    """

    SERVICES = {
        LLMMode.LIVE: LLMService(
            name="ollama-live",
            port=11434,
            model="qwen2.5:32b-instruct-q4_K_M",
            description="Fast chat and general queries (Qwen 32B instruct, 32k context)"
        ),
        LLMMode.THINK: LLMService(
            name="ollama-think",
            port=11435,
            model="qwen2.5:32b-instruct-q4_K_M",
            description="Deep reasoning and chain-of-thought (Qwen 32B instruct, 32k context)"
        ),
        LLMMode.DEEP: LLMService(
            name="ollama-live",
            port=11434,
            model="qwen2.5:32b-instruct-q4_K_M",
            description="Deep analysis and investigations (Qwen 32B instruct, 32k context)"
        ),
        LLMMode.CODE: LLMService(
            name="ollama-think",
            port=11435,
            model="qwen2.5:32b-instruct-q4_K_M",
            description="Code generation and completion (Qwen 32B instruct, 32k context)"
        ),
    }

    def __init__(self):
        self.dashboard_url = "http://localhost:8765"
        self._remote_llm_cache: Optional[Tuple[bool, str]] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 5.0  # seconds

    def get_service(self, mode: LLMMode) -> LLMService:
        """Get the LLM service configuration for a given mode."""
        return self.SERVICES[mode]

    def check_remote_llm(self, use_cache: bool = True) -> Tuple[bool, str]:
        """
        Check if remote LLM is available via dashboard.

        Args:
            use_cache: Whether to use cached result (cached for 5s)

        Returns:
            tuple[bool, str]: (enabled, model_name)
        """
        # Check cache
        if use_cache and self._remote_llm_cache is not None:
            age = time.time() - self._cache_time
            if age < self._cache_ttl:
                return self._remote_llm_cache

        # Query dashboard
        try:
            import requests
            r = requests.get(
                f"{self.dashboard_url}/api/curiosity/remote-llm-config",
                timeout=2
            )
            if r.status_code == 200:
                config = r.json()
                enabled = config.get("enabled", False)
                model = config.get("selected_model", "qwen2.5:72b")
                result = (enabled, model)

                # Update cache
                self._remote_llm_cache = result
                self._cache_time = time.time()

                return result
        except Exception as e:
            logger.debug(f"Remote LLM check failed: {e}")

        return (False, "")

    def query_remote_llm(
        self,
        prompt: str,
        model: Optional[str] = None,
        stream: bool = False
    ) -> Tuple[bool, str]:
        """
        Query remote LLM via dashboard proxy.

        Args:
            prompt: The prompt to send
            model: Model to use (defaults to configured remote model)
            stream: Whether to stream response (not yet supported)

        Returns:
            tuple[bool, str]: (success, response_text_or_error)
        """
        if stream:
            return (False, "Streaming not supported for remote LLM")

        try:
            import requests

            if not model:
                _, model = self.check_remote_llm()
                if not model:
                    model = "qwen2.5:72b"

            r = requests.post(
                f"{self.dashboard_url}/api/curiosity/remote-query",
                json={"model": model, "prompt": prompt, "enabled": True},
                timeout=120
            )

            if r.status_code == 200:
                data = r.json()
                if data.get("success"):
                    return (True, data.get("response", ""))
                else:
                    return (False, f"Remote LLM error: {data.get('error', 'Unknown')}")
            else:
                return (False, f"Dashboard proxy error: HTTP {r.status_code}")

        except Exception as e:
            return (False, f"Remote LLM query failed: {e}")

    def check_service_health(self, mode: LLMMode) -> Tuple[bool, str]:
        """
        Check if Ollama service is running and responsive.

        Args:
            mode: Which LLM service to check

        Returns:
            tuple[bool, str]: (is_healthy, error_message)
        """
        service = self.get_service(mode)
        try:
            import requests
            r = requests.get(f"{service.url}/api/tags", timeout=2)
            if r.status_code == 200:
                return (True, "")
            else:
                return (False, f"Ollama {service.name} returned status {r.status_code}")
        except requests.exceptions.Timeout:
            return (False, f"Ollama {service.name} is not responding (timeout)")
        except requests.exceptions.ConnectionError:
            return (False, f"Ollama {service.name} is not running (connection refused)")
        except Exception as e:
            return (False, f"Ollama {service.name} health check failed: {e}")

    def query_local_llm(
        self,
        prompt: str,
        mode: LLMMode = LLMMode.LIVE,
        stream: bool = False,
        **kwargs
    ) -> Tuple[bool, str]:
        """
        Query local Ollama service.

        Args:
            prompt: The prompt to send
            mode: Which LLM mode to use
            stream: Whether to stream response
            **kwargs: Additional parameters for Ollama API

        Returns:
            tuple[bool, str]: (success, response_text_or_error)
        """
        service = self.get_service(mode)

        is_healthy, error_msg = self.check_service_health(mode)
        if not is_healthy:
            logger.error(f"[llm_router] {error_msg}")
            return (False, error_msg)

        try:
            import requests

            payload = {
                "model": service.model,
                "prompt": prompt,
                "stream": stream,
                **kwargs
            }

            r = requests.post(
                f"{service.url}/api/generate",
                json=payload,
                timeout=120,
                stream=stream
            )

            if r.status_code == 200:
                if stream:
                    return (True, r.iter_lines())
                else:
                    response = r.json().get("response", "")
                    return (True, response)
            else:
                return (False, f"Ollama error: HTTP {r.status_code}")

        except Exception as e:
            return (False, f"Local LLM query failed: {e}")

    def query(
        self,
        prompt: str,
        mode: LLMMode = LLMMode.LIVE,
        prefer_remote: bool = True,
        stream: bool = False,
        **kwargs
    ) -> Tuple[bool, str, str]:
        """
        Query LLM with automatic routing.

        This is the main entry point for all LLM queries in KLoROS.

        Strategy:
        1. Check if remote LLM is available (cached for 5s)
        2. Try remote LLM first if enabled and prefer_remote=True
        3. Fall back to local Ollama if remote fails or disabled
        4. Use correct local service based on mode

        Args:
            prompt: The prompt to send
            mode: Which LLM mode to use (live/think/deep/code)
            prefer_remote: Whether to prefer remote LLM over local
            stream: Whether to stream response
            **kwargs: Additional parameters for Ollama API

        Returns:
            tuple[bool, str, str]: (success, response_text_or_error, source)
                where source is "remote", "local:{service_name}", or "error"
        """
        # Try remote LLM first if preferred
        if prefer_remote:
            remote_enabled, remote_model = self.check_remote_llm()
            if remote_enabled:
                logger.debug(f"Trying remote LLM: {remote_model}")
                success, response = self.query_remote_llm(prompt, stream=stream)
                if success:
                    logger.info(f"LLM query successful via remote: {remote_model}")
                    return (True, response, "remote")
                else:
                    logger.warning(f"Remote LLM failed: {response}, falling back to local")

        # Fall back to local Ollama
        service = self.get_service(mode)
        logger.debug(f"Trying local LLM: {service.name} on port {service.port}")
        success, response = self.query_local_llm(prompt, mode, stream, **kwargs)

        if success:
            logger.info(f"LLM query successful via local: {service.name}")
            return (True, response, f"local:{service.name}")
        else:
            logger.error(f"Local LLM failed: {response}")
            return (False, response, "error")

    def get_available_services(self) -> Dict[str, Any]:
        """
        Get information about all available LLM services.

        Returns:
            dict: Service availability and configuration
        """
        remote_enabled, remote_model = self.check_remote_llm()

        local_services = {}
        for mode, service in self.SERVICES.items():
            local_services[mode.value] = {
                "name": service.name,
                "port": service.port,
                "model": service.model,
                "description": service.description,
                "url": service.url
            }

        return {
            "remote": {
                "enabled": remote_enabled,
                "model": remote_model,
                "url": f"{self.dashboard_url}/api/curiosity/remote-query"
            },
            "local": local_services
        }


# Global router instance
_router = None


def get_router() -> LLMRouter:
    """Get the global LLM router instance."""
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
