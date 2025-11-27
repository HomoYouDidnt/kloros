#!/usr/bin/env python3
"""KLoROS Voice LLM Integration Zooid - Unified LLM adapter with remote/local fallback.

This zooid handles:
- Remote LLM integration (dashboard proxy to ALTIMITOS)
- Local Ollama fallback
- Streaming and non-streaming response modes
- Timeout and retry logic
- Tool call integration

ChemBus Signals:
- Emits: VOICE.LLM.RESPONSE (response, model, latency, tool_calls)
- Emits: VOICE.LLM.ERROR (error_type, details, attempt_count)
- Emits: VOICE.LLM.READY (available_backends, default_model)
- Emits: VOICE.LLM.SHUTDOWN (stats)
- Listens: VOICE.ORCHESTRATOR.LLM.REQUEST (prompt, mode, temperature, max_tokens)
"""
from __future__ import annotations

import os
import sys
import time
import json
import signal
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, Literal
from datetime import datetime

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.orchestration.core.umn_bus import UMNPub as ChemPub, UMNSub as ChemSub


class LLMZooid:
    """LLM Integration zooid with unified adapter for remote/local backends."""

    def __init__(self):
        self.zooid_name = "kloros-voice-llm"
        self.niche = "voice.llm"

        self.chem_pub = ChemPub()

        self.running = True
        self.enable_llm = int(os.getenv("KLR_ENABLE_LLM", "1"))

        self.remote_llm_enabled = False
        self.remote_llm_model = os.getenv("KLR_REMOTE_LLM_MODEL", "qwen2.5:72b")
        self.dashboard_url = os.getenv("KLR_DASHBOARD_URL", "http://localhost:5002")

        self.ollama_model = os.getenv("KLR_OLLAMA_MODEL", "main")
        self.ollama_url = os.getenv("KLR_OLLAMA_URL", "http://localhost:11434")
        self.ollama_api_endpoint = f"{self.ollama_url}/api/generate"

        self.remote_timeout = int(os.getenv("KLR_REMOTE_LLM_TIMEOUT", "120"))
        self.local_timeout = int(os.getenv("KLR_LOCAL_LLM_TIMEOUT", "60"))
        self.max_retries = int(os.getenv("KLR_LLM_MAX_RETRIES", "1"))

        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "remote_requests": 0,
            "local_requests": 0,
            "average_latency": 0.0,
            "latencies": [],
            "tool_calls": 0,
        }

        print(f"[llm] Initialized: enable={self.enable_llm}, remote_model={self.remote_llm_model}, local_model={self.ollama_model}")

    def start(self):
        """Start the LLM zooid and subscribe to ChemBus signals."""
        print(f"[llm] Starting {self.zooid_name}")

        if not self.enable_llm:
            print("[llm] LLM integration disabled via KLR_ENABLE_LLM=0")
            return

        self._check_remote_llm_config()
        self._subscribe_to_signals()

        available_backends = []
        if self.remote_llm_enabled:
            available_backends.append("remote")
        available_backends.append("ollama")

        self.chem_pub.emit(
            "VOICE.LLM.READY",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "available_backends": available_backends,
                "default_model": self.remote_llm_model if self.remote_llm_enabled else self.ollama_model,
                "remote_enabled": self.remote_llm_enabled,
                "local_model": self.ollama_model,
            }
        )

        print(f"[llm] {self.zooid_name} ready (backends: {', '.join(available_backends)})")

    def _check_remote_llm_config(self) -> None:
        """Check dashboard for remote LLM configuration."""
        try:
            r = requests.get(f"{self.dashboard_url}/api/curiosity/remote-llm-config", timeout=2)
            if r.status_code == 200:
                config = r.json()
                self.remote_llm_enabled = config.get("enabled", False)
                self.remote_llm_model = config.get("selected_model", self.remote_llm_model)
                if self.remote_llm_enabled:
                    print(f"[llm] Remote LLM enabled: {self.remote_llm_model}")
            else:
                print(f"[llm] Remote LLM config unavailable: HTTP {r.status_code}")
                self.remote_llm_enabled = False
        except Exception as e:
            print(f"[llm] Remote LLM config check failed: {e}")
            self.remote_llm_enabled = False

    def _subscribe_to_signals(self):
        """Subscribe to ChemBus signals for LLM requests."""
        self.llm_request_sub = ChemSub(
            "VOICE.ORCHESTRATOR.LLM.REQUEST",
            self._on_llm_request,
            zooid_name=self.zooid_name,
            niche=self.niche
        )

        print("[llm] Subscribed to ChemBus signals")

    def _on_llm_request(self, event: dict):
        """Handle VOICE.ORCHESTRATOR.LLM.REQUEST signal and generate LLM response.

        Args:
            event: ChemBus event with LLM request
                - facts.prompt: Input prompt for LLM
                - facts.mode: "streaming" or "non-streaming" (default: "non-streaming")
                - facts.temperature: Temperature for generation (default: 0.8)
                - facts.max_tokens: Max tokens to generate (default: None)
                - facts.model: Override model selection (default: None)
                - incident_id: Event correlation ID
        """
        if not self.running:
            return

        try:
            facts = event.get("facts", {})
            prompt = facts.get("prompt", "")
            mode = facts.get("mode", "non-streaming")
            temperature = facts.get("temperature", 0.8)
            max_tokens = facts.get("max_tokens")
            model_override = facts.get("model")
            incident_id = event.get("incident_id")

            if not prompt:
                print("[llm] ERROR: No prompt in LLM.REQUEST event")
                self._emit_error("missing_prompt", "No prompt provided in request", 0, incident_id)
                return

            start_time = time.time()
            self.stats["total_requests"] += 1

            attempt_count = 0
            response = None
            error = None
            used_backend = None
            used_model = None

            for attempt in range(self.max_retries + 1):
                attempt_count = attempt + 1

                self._check_remote_llm_config()

                if self.remote_llm_enabled and not model_override:
                    success, resp = self._query_remote_llm(
                        prompt, temperature=temperature, max_tokens=max_tokens
                    )
                    if success:
                        response = resp
                        used_backend = "remote"
                        used_model = self.remote_llm_model
                        self.stats["remote_requests"] += 1
                        break
                    else:
                        error = resp
                        print(f"[llm] Remote LLM attempt {attempt_count} failed: {resp}")

                try:
                    if mode == "streaming":
                        resp = self._query_ollama_streaming(
                            prompt, temperature=temperature, max_tokens=max_tokens,
                            model=model_override or self.ollama_model
                        )
                    else:
                        resp = self._query_ollama(
                            prompt, temperature=temperature, max_tokens=max_tokens,
                            model=model_override or self.ollama_model
                        )

                    if not resp.startswith("Error:") and not resp.startswith("Ollama error:"):
                        response = resp
                        used_backend = "ollama"
                        used_model = model_override or self.ollama_model
                        self.stats["local_requests"] += 1
                        break
                    else:
                        error = resp
                        print(f"[llm] Ollama attempt {attempt_count} failed: {resp}")

                except Exception as e:
                    error = f"Ollama exception: {e}"
                    print(f"[llm] Ollama attempt {attempt_count} exception: {e}")

            latency = time.time() - start_time

            if response is not None:
                self.stats["successful_requests"] += 1
                self.stats["latencies"].append(latency)
                if len(self.stats["latencies"]) > 100:
                    self.stats["latencies"] = self.stats["latencies"][-100:]

                old_avg = self.stats["average_latency"]
                total = self.stats["successful_requests"]
                self.stats["average_latency"] = (old_avg * (total - 1) + latency) / total

                self._emit_response(
                    prompt=prompt,
                    response=response,
                    model=used_model,
                    backend=used_backend,
                    latency=latency,
                    temperature=temperature,
                    incident_id=incident_id
                )

                print(f"[llm] Generated response ({latency:.2f}s, {used_backend}/{used_model}): {response[:60]}...")

            else:
                self.stats["failed_requests"] += 1
                self._emit_error(
                    "generation_failed",
                    error or "All LLM backends failed",
                    attempt_count,
                    incident_id
                )
                print(f"[llm] ERROR: All {attempt_count} attempts failed: {error}")

        except Exception as e:
            print(f"[llm] ERROR during request handling: {e}")
            print(f"[llm] Traceback: {traceback.format_exc()}")
            self.stats["failed_requests"] += 1
            self._emit_error("request_handling_failed", str(e), 0, event.get("incident_id"))

    def _query_remote_llm(
        self, prompt: str, temperature: float = 0.8, max_tokens: Optional[int] = None
    ) -> tuple[bool, str]:
        """Query remote LLM via dashboard proxy.

        Args:
            prompt: Input prompt
            temperature: Generation temperature
            max_tokens: Max tokens to generate

        Returns:
            (success: bool, response: str)
        """
        try:
            payload = {
                "model": self.remote_llm_model,
                "prompt": prompt,
                "enabled": True,
                "temperature": temperature,
            }
            if max_tokens:
                payload["max_tokens"] = max_tokens

            r = requests.post(
                f"{self.dashboard_url}/api/curiosity/remote-query",
                json=payload,
                timeout=self.remote_timeout
            )

            if r.status_code == 200:
                data = r.json()
                if data.get("success"):
                    return (True, data.get("response", ""))
                else:
                    return (False, f"Remote LLM error: {data.get('error', 'Unknown')}")
            else:
                return (False, f"Dashboard proxy error: HTTP {r.status_code}")

        except requests.Timeout:
            return (False, f"Remote LLM timeout ({self.remote_timeout}s)")
        except Exception as e:
            return (False, f"Remote LLM query failed: {e}")

    def _query_ollama(
        self, prompt: str, temperature: float = 0.8, max_tokens: Optional[int] = None,
        model: str = None
    ) -> str:
        """Query local Ollama (non-streaming).

        Args:
            prompt: Input prompt
            temperature: Generation temperature
            max_tokens: Max tokens to generate (mapped to num_predict)
            model: Model to use (default: self.ollama_model)

        Returns:
            Response text or error message
        """
        try:
            payload = {
                "model": model or self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                }
            }

            if max_tokens:
                payload["options"]["num_predict"] = max_tokens

            try:
                from src.config.models_config import get_ollama_context_size
                payload["options"]["num_ctx"] = get_ollama_context_size(check_vram=False)
            except ImportError:
                payload["options"]["num_ctx"] = 8192

            r = requests.post(
                self.ollama_api_endpoint,
                json=payload,
                timeout=self.local_timeout
            )

            if r.status_code == 200:
                response_data = r.json()
                return response_data.get("response", "").strip()
            else:
                return f"Error: Ollama HTTP {r.status_code}"

        except requests.Timeout:
            return f"Ollama error: timeout ({self.local_timeout}s)"
        except requests.RequestException as e:
            return f"Ollama error: {e}"

    def _query_ollama_streaming(
        self, prompt: str, temperature: float = 0.8, max_tokens: Optional[int] = None,
        model: str = None
    ) -> str:
        """Query local Ollama (streaming).

        Args:
            prompt: Input prompt
            temperature: Generation temperature
            max_tokens: Max tokens to generate
            model: Model to use

        Returns:
            Complete response text or error message
        """
        try:
            payload = {
                "model": model or self.ollama_model,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": temperature,
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                }
            }

            if max_tokens:
                payload["options"]["num_predict"] = max_tokens

            try:
                from src.config.models_config import get_ollama_context_size
                payload["options"]["num_ctx"] = get_ollama_context_size(check_vram=False)
            except ImportError:
                payload["options"]["num_ctx"] = 8192

            r = requests.post(
                self.ollama_api_endpoint,
                json=payload,
                stream=True,
                timeout=self.local_timeout
            )

            if r.status_code != 200:
                return f"Error: Ollama HTTP {r.status_code}"

            complete_response = ""
            for line in r.iter_lines():
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    complete_response += token

                    if chunk.get("done", False):
                        break

                except json.JSONDecodeError as e:
                    print(f"[llm] JSON decode error: {e}")
                    continue

            return complete_response.strip()

        except requests.Timeout:
            return f"Ollama error: timeout ({self.local_timeout}s)"
        except requests.RequestException as e:
            return f"Ollama error: {e}"

    def _emit_response(
        self,
        prompt: str,
        response: str,
        model: str,
        backend: str,
        latency: float,
        temperature: float,
        incident_id: Optional[str]
    ):
        """Emit VOICE.LLM.RESPONSE signal.

        Args:
            prompt: Original prompt
            response: Generated response
            model: Model used
            backend: Backend used (remote/ollama)
            latency: Generation latency in seconds
            temperature: Temperature used
            incident_id: Event correlation ID
        """
        self.chem_pub.emit(
            "VOICE.LLM.RESPONSE",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "prompt": prompt[:200],
                "response": response,
                "model": model,
                "backend": backend,
                "latency": latency,
                "temperature": temperature,
                "timestamp": datetime.now().isoformat(),
            },
            incident_id=incident_id
        )

    def _emit_error(
        self, error_type: str, details: str, attempt_count: int, incident_id: Optional[str]
    ):
        """Emit VOICE.LLM.ERROR signal.

        Args:
            error_type: Type of error
            details: Error details
            attempt_count: Number of attempts made
            incident_id: Event correlation ID
        """
        self.chem_pub.emit(
            "VOICE.LLM.ERROR",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "error_type": error_type,
                "details": details,
                "attempt_count": attempt_count,
                "remote_enabled": self.remote_llm_enabled,
                "timestamp": datetime.now().isoformat(),
            },
            incident_id=incident_id
        )

    def get_stats(self) -> dict:
        """Get LLM statistics.

        Returns:
            Dictionary with LLM statistics
        """
        avg_latency = (
            sum(self.stats["latencies"]) / len(self.stats["latencies"])
            if self.stats["latencies"] else 0.0
        )

        return {
            **self.stats,
            "average_latency": avg_latency,
            "remote_enabled": self.remote_llm_enabled,
        }

    def shutdown(self):
        """Graceful shutdown of LLM zooid."""
        print(f"[llm] Shutting down {self.zooid_name}")
        self.running = False

        final_stats = self.get_stats()
        print(f"[llm] Final statistics: {final_stats}")

        self.chem_pub.emit(
            "VOICE.LLM.SHUTDOWN",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "stats": final_stats,
            }
        )

        if hasattr(self, 'llm_request_sub'):
            self.llm_request_sub.close()
        self.chem_pub.close()

        print(f"[llm] {self.zooid_name} shutdown complete")


def main():
    """Main entry point for LLM zooid daemon."""
    print("[llm] Starting KLoROS Voice LLM Integration Zooid")

    zooid = LLMZooid()

    def signal_handler(signum, frame):
        print(f"[llm] Received signal {signum}, shutting down...")
        zooid.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    zooid.start()

    try:
        while zooid.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[llm] Interrupted by user")
    finally:
        zooid.shutdown()


if __name__ == "__main__":
    main()
