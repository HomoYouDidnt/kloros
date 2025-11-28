"""
Single source of truth for ALL AI model configurations in KLoROS.

This module loads configuration from /home/kloros/config/models.toml and provides
getter functions for all components. All models should be accessed through this module.
"""

import os


# Lazy-loaded SSOT instance
_SSOT = None
_SSOT_LOAD_ATTEMPTED = False


def _get_ssot():
    """Get or create SSOT instance."""
    global _SSOT, _SSOT_LOAD_ATTEMPTED
    if _SSOT is None and not _SSOT_LOAD_ATTEMPTED:
        _SSOT_LOAD_ATTEMPTED = True
        try:
            from src.ssot.loader import get_ssot
            _SSOT = get_ssot()
        except Exception:
            # SSOT module not available - using fallback config (env vars + defaults)
            _SSOT = None
    return _SSOT


# ============================================================================
# EMBEDDING MODELS
# ============================================================================

def get_embedder_model() -> str:
    """Get the primary embedder model name."""
    ssot = _get_ssot()
    if ssot:
        return ssot.get_embedder_model()
    return os.getenv("KLR_EMBEDDER_MODEL", "BAAI/bge-small-en-v1.5")


def get_embedder_fallbacks() -> list[str]:
    """Get list of fallback embedder models."""
    ssot = _get_ssot()
    if ssot:
        return ssot.get_embedder_fallbacks()
    return [
        "all-MiniLM-L6-v2",
        "all-distilroberta-v1",
        "all-MiniLM-L12-v2"
    ]


def get_embedder_trust_remote_code() -> bool:
    """Get trust_remote_code flag for embedder models."""
    ssot = _get_ssot()
    if ssot:
        return ssot.get_embedder_trust_remote_code()
    return False


# Legacy constants for backward compatibility
EMBEDDER_MODEL = get_embedder_model()
EMBEDDER_FALLBACKS = get_embedder_fallbacks()


# ============================================================================
# LLM / REASONING MODELS
# ============================================================================

# Cache for remote Ollama availability check
_remote_ollama_cache = {"url": None, "timestamp": 0, "ttl": 30}

# State tracking for TTS announcements (None=unknown, "disabled", "unavailable", "connected")
_remote_ollama_state = {"last_state": None}

# Cache for remote Judge availability check
_remote_judge_cache = {"url": None, "timestamp": 0, "ttl": 30}


def _announce_ollama_state_change(new_state: str):
    """Announce Ollama state changes via TTS (non-blocking)."""
    import subprocess
    import tempfile

    # Only announce if state actually changed
    if _remote_ollama_state["last_state"] == new_state:
        return

    _remote_ollama_state["last_state"] = new_state

    # Map states to announcements
    messages = {
        "disabled": "Remote disabled",
        "connected": "Connected to AltimitOS",
        "unavailable": "AltimitOS unavailable"
    }

    message = messages.get(new_state)
    if message:
        try:
            import threading
            model_path = "/home/kloros/models/piper/glados_piper_medium.onnx"
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name

            def _speak_and_cleanup():
                try:
                    piper_proc = subprocess.run(
                        ["piper", "-m", model_path, "-f", tmp_path],
                        input=message.encode(),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    if piper_proc.returncode == 0:
                        subprocess.run(
                            ["aplay", "-q", tmp_path],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

            threading.Thread(target=_speak_and_cleanup, daemon=True).start()
        except Exception:
            pass


def _check_remote_ollama() -> str | None:
    """
    Check if remote Ollama (gaming rig) is available.

    Uses cached result for 30 seconds to avoid excessive network checks.
    Loads gaming rig config from /home/kloros/.kloros/judge_config.json.

    Returns:
        Remote Ollama URL if available, None otherwise
    """
    import time
    import json
    from pathlib import Path

    # Check cache first
    now = time.time()
    if now - _remote_ollama_cache["timestamp"] < _remote_ollama_cache["ttl"]:
        return _remote_ollama_cache["url"]

    # Load gaming rig config
    config_path = Path("/home/kloros/.kloros/judge_config.json")
    if not config_path.exists():
        _remote_ollama_cache["url"] = None
        _remote_ollama_cache["timestamp"] = now
        return None

    try:
        with open(config_path) as f:
            config = json.load(f)

        # Check if remote Ollama URL is configured
        ollama_url = config.get("ollama_remote_url")

        if not ollama_url:
            _remote_ollama_cache["url"] = None
            _remote_ollama_cache["timestamp"] = now
            return None

        # Check if user enabled remote via toggle service
        import requests
        toggle_host = ollama_url.split(':')[1].replace('//', '')  # Extract IP
        try:
            status_resp = requests.get(
                f"http://{toggle_host}:8888/status",
                timeout=1  # Quick check
            )
            if status_resp.status_code == 200:
                enabled = status_resp.json().get("enabled", True)
                if not enabled:
                    # User explicitly disabled remote via Stream Deck
                    _announce_ollama_state_change("disabled")
                    _remote_ollama_cache["url"] = None
                    _remote_ollama_cache["timestamp"] = now
                    return None
        except Exception:
            # Toggle service not reachable - assume enabled (fail-open)
            pass

        # Test connectivity with quick ping to /api/tags
        # User controls starting/stopping Ollama - we just detect if it's listening
        try:
            response = requests.get(
                f"{ollama_url}/api/tags",
                timeout=2
            )
            if response.status_code == 200:
                # Remote Ollama is alive and listening!
                _announce_ollama_state_change("connected")
                _remote_ollama_cache["url"] = ollama_url
                _remote_ollama_cache["timestamp"] = now
                return ollama_url
        except Exception:
            pass

        # Remote not listening (user may have stopped it for gaming)
        _announce_ollama_state_change("unavailable")
        _remote_ollama_cache["url"] = None
        _remote_ollama_cache["timestamp"] = now
        return None

    except Exception:
        _announce_ollama_state_change("unavailable")
        _remote_ollama_cache["url"] = None
        _remote_ollama_cache["timestamp"] = now
        return None


def _check_remote_judge() -> str | None:
    """
    Check if remote vLLM Judge (gaming rig) is available.

    Uses cached result for 30 seconds to avoid excessive network checks.
    Loads gaming rig config from /home/kloros/.kloros/judge_config.json.

    Returns:
        Remote Judge URL if available, None otherwise
    """
    import time
    import json
    from pathlib import Path

    # Check cache first
    now = time.time()
    if now - _remote_judge_cache["timestamp"] < _remote_judge_cache["ttl"]:
        return _remote_judge_cache["url"]

    # Load gaming rig config
    config_path = Path("/home/kloros/.kloros/judge_config.json")
    if not config_path.exists():
        _remote_judge_cache["url"] = None
        _remote_judge_cache["timestamp"] = now
        return None

    try:
        with open(config_path) as f:
            config = json.load(f)

        # Check if judge URL is configured
        judge_url = config.get("judge_url")

        if not judge_url:
            _remote_judge_cache["url"] = None
            _remote_judge_cache["timestamp"] = now
            return None

        # Test connectivity with quick ping to /health or /v1/models
        # User controls starting/stopping judge - we just detect if it's listening
        import requests
        try:
            # Try health endpoint first
            response = requests.get(
                judge_url.replace("/v1/chat/completions", "/health"),
                timeout=2
            )
            if response.status_code == 200:
                # Remote Judge is alive and listening!
                _remote_judge_cache["url"] = judge_url
                _remote_judge_cache["timestamp"] = now
                return judge_url
        except Exception:
            pass

        # Remote not listening (user may have stopped it for gaming)
        _remote_judge_cache["url"] = None
        _remote_judge_cache["timestamp"] = now
        return None

    except Exception:
        _remote_judge_cache["url"] = None
        _remote_judge_cache["timestamp"] = now
        return None


def get_judge_url() -> str | None:
    """
    Get the vLLM Judge URL with automatic remote detection.

    Checks if remote Judge (gaming rig) is available.
    Returns None if judge unavailable (signals to queue for later).

    Returns:
        Judge URL if available, None if unavailable
    """
    remote_url = _check_remote_judge()
    return remote_url  # None if unavailable - caller should queue


def get_ollama_model() -> str:
    """Get the Ollama model for reasoning/generation."""
    ssot = _get_ssot()
    if ssot:
        return ssot.get_ollama_model()
    return os.getenv("OLLAMA_MODEL", "meta-llama/Llama-3.1-8B-Instruct")


def get_ollama_url() -> str:
    """
    Get the Ollama API base URL with automatic remote failover.

    ALWAYS checks remote gaming rig first (100.67.244.66:11434),
    then falls back to local Ollama if remote is unreachable.

    Returns:
        Ollama API URL (remote if available, local otherwise)
    """
    remote_url = _check_remote_ollama()
    if remote_url:
        return remote_url

    ssot = _get_ssot()
    if ssot:
        return ssot.get_ollama_url()

    return os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")


def get_ollama_context_size(check_vram: bool = False) -> int:
    """
    Get the Ollama context window size (num_ctx).

    Default: 16384 (16k) - sweet spot for RTX 3060 12GB
    - 4096: Too small, causes truncation
    - 16384: Optimal (KV ~3GB, total ~11.9GB, safe headroom)
    - 32768: Won't fit on 12GB (KV ~6GB, total ~14.5GB)

    Args:
        check_vram: If True, dynamically cap based on available VRAM

    Returns:
        Context size in tokens
    """
    ssot = _get_ssot()
    if ssot and hasattr(ssot, "get_ollama_context_size"):
        return ssot.get_ollama_context_size()

    # Base context size from environment
    base_ctx = int(os.getenv("OLLAMA_NUM_CTX", "16384"))

    # Dynamic VRAM-aware capping
    if check_vram:
        try:
            # Estimate: KV cache scales linearly with context
            # RTX 3060 12GB safe limit: ~11.5 GB total
            # Weights: 7.7 GB, Compute: 0.4 GB, leaves 3.4 GB for KV
            # KV @ 4k = 0.75 GB → scale factor = 0.1875 GB per 1k ctx
            #
            # Safe contexts:
            # - 8k:  ~1.5 GB KV → 9.6 GB total ✓
            # - 12k: ~2.25 GB KV → 10.35 GB total ✓
            # - 16k: ~3.0 GB KV → 11.1 GB total ✓ (tight)
            # - 32k: ~6.0 GB KV → 14.1 GB total ✗ (OOM)

            available_for_kv = 3.4  # GB (conservative)
            kv_per_1k_ctx = 0.1875  # GB

            max_safe_ctx = int((available_for_kv / kv_per_1k_ctx) * 1000)

            if base_ctx > max_safe_ctx:
                import logging
                logging.warning(
                    f"Capping num_ctx from {base_ctx} to {max_safe_ctx} "
                    f"to avoid VRAM pressure (estimated KV would exceed {available_for_kv:.1f}GB)"
                )
                return max_safe_ctx

        except Exception as e:
            import logging
            logging.debug(f"VRAM check failed, using base context: {e}")

    return base_ctx


def get_ollama_url_for_mode(mode: str = None) -> str:
    """Get Ollama URL - defaults to local.

    Args:
        mode: 'live' for fast responses, 'think' for deep analysis,
              'deep' for background async, or 'code' for code generation

    Returns:
        Local Ollama API URL
    """
    return os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")


def get_available_models(ollama_url: str) -> list[str]:
    """
    Query Ollama API to get list of available models.

    Args:
        ollama_url: Ollama server URL

    Returns:
        List of available model names, empty list on failure
    """
    import requests
    try:
        response = requests.get(f"{ollama_url}/api/tags", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
    except Exception:
        pass
    return []


def select_best_model_for_task(task_type: str, ollama_url: str = None) -> str:
    """
    Select best available model for task type by querying API.

    Args:
        task_type: 'code', 'reasoning', 'fast', 'deep'
        ollama_url: Ollama server URL (defaults to get_ollama_url())

    Returns:
        Best available model name for the task
    """
    if ollama_url is None:
        ollama_url = get_ollama_url()

    available = get_available_models(ollama_url)

    # Task-specific preferences (best to worst)
    preferences = {
        'code': [
            'qwen2.5-coder:32b',
            'qwen2.5-coder:14b',
            'qwen2.5-coder:7b',
            'deepseek-r1:14b',
            'deepseek-r1:7b',
        ],
        'reasoning': [
            'deepseek-r1:14b',
            'qwen2.5:14b-instruct-q4_0',
            'qwen2.5-coder:32b',
            'deepseek-r1:7b',
            'qwen2.5-coder:7b',
        ],
        'fast': [
            'qwen2.5-coder:7b',
            'deepseek-r1:7b',
            'qwen2.5:7b-instruct-q4_K_M',
        ],
        'deep': [
            'qwen2.5-coder:32b',
            'deepseek-r1:14b',
            'qwen2.5:14b-instruct-q4_0',
        ]
    }

    # Get preferences for this task type
    task_prefs = preferences.get(task_type, preferences['fast'])

    # Return first preference that's available
    for pref in task_prefs:
        if pref in available:
            return pref

    # Fallback: return first available model or default
    if available:
        return available[0]
    return os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")


def get_ollama_model_for_mode(mode: str = None) -> str:
    """Get Ollama model based on mode (live/think/deep/code).

    Args:
        mode: 'live' for fast responses, 'think' for deep analysis,
              'deep' for background async, or 'code' for code generation

    Returns:
        Model name for the specified mode
    """
    mode = mode or os.getenv("KLR_MODEL_MODE", "live")

    # Map mode to task type
    task_map = {
        'code': 'code',
        'think': 'reasoning',
        'deep': 'deep',
        'live': 'fast'
    }

    task_type = task_map.get(mode, 'fast')
    return select_best_model_for_task(task_type)


OLLAMA_MODEL = get_ollama_model()
OLLAMA_URL = get_ollama_url()


# ============================================================================
# SPEECH-TO-TEXT MODELS
# ============================================================================

def get_whisper_model() -> str:
    """Get the Whisper model size for STT."""
    ssot = _get_ssot()
    if ssot:
        return ssot.get_whisper_model()
    return os.getenv("KLR_WHISPER_MODEL", "tiny")


def get_vosk_model_path() -> str:
    """Get the Vosk model path for wake word detection."""
    ssot = _get_ssot()
    if ssot and hasattr(ssot.models.get("stt", {}).get("vosk", {}), "model_path"):
        return ssot.models["stt"]["vosk"]["model_path"]
    return "/home/kloros/models/vosk/model"


WHISPER_MODEL = get_whisper_model()
VOSK_MODEL_PATH = get_vosk_model_path()


# ============================================================================
# TEXT-TO-SPEECH MODELS
# ============================================================================

def get_piper_voice() -> str:
    """Get the Piper voice model."""
    ssot = _get_ssot()
    if ssot:
        return ssot.get_piper_voice()
    return os.getenv("KLR_PIPER_VOICE", "en_US-lessac-medium")


def get_xtts_model() -> str:
    """Get the XTTS v2 model."""
    return "tts_models/multilingual/multi-dataset/xtts_v2"


def get_kokoro_model() -> str:
    """Get the Kokoro TTS model."""
    return "kokoro-v0_19"


PIPER_VOICE = get_piper_voice()
XTTS_MODEL = get_xtts_model()
KOKORO_MODEL = get_kokoro_model()


# ============================================================================
# SPEAKER IDENTIFICATION MODELS
# ============================================================================

def get_speaker_embedding_model() -> str:
    """Get the speaker embedding model."""
    return "speechbrain/spkrec-ecapa-voxceleb"


SPEAKER_EMBEDDING_MODEL = get_speaker_embedding_model()


# ============================================================================
# UTILITIES
# ============================================================================

def get_all_models() -> dict:
    """Get dictionary of all configured models."""
    return {
        "embedder": {
            "primary": get_embedder_model(),
            "fallbacks": get_embedder_fallbacks()
        },
        "llm": {
            "ollama_model": get_ollama_model(),
            "ollama_url": get_ollama_url()
        },
        "stt": {
            "whisper": get_whisper_model(),
            "vosk_path": get_vosk_model_path()
        },
        "tts": {
            "piper": get_piper_voice(),
            "xtts": get_xtts_model(),
            "kokoro": get_kokoro_model()
        },
        "speaker": {
            "embedding": get_speaker_embedding_model()
        }
    }


# ============================================================================
# REMOTE LLM INTEGRATION
# ============================================================================

def check_remote_llm_available() -> tuple[bool, str]:
    """
    Check if remote LLM is enabled via dashboard.

    Returns:
        tuple[bool, str]: (enabled, model_name)
    """
    try:
        import requests
        dashboard_url = "http://localhost:8765"
        r = requests.get(f"{dashboard_url}/api/curiosity/remote-llm-config", timeout=2)
        if r.status_code == 200:
            config = r.json()
            enabled = config.get("enabled", False)
            model = config.get("selected_model", "qwen2.5:72b")
            return (enabled, model)
    except Exception:
        pass
    return (False, "")


def query_remote_llm(prompt: str, model: str = None, stream: bool = False) -> tuple[bool, str]:
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
        # Streaming not yet implemented for remote LLM
        return (False, "Streaming not supported for remote LLM")

    try:
        import requests
        dashboard_url = "http://localhost:8765"

        if not model:
            _, model = check_remote_llm_available()
            if not model:
                model = "qwen2.5:72b"

        r = requests.post(
            f"{dashboard_url}/api/curiosity/remote-query",
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


# ============================================================================
# LLAMA.CPP CONFIGURATION
# ============================================================================

def get_llama_url_for_mode(mode: str = "live") -> str:
    """
    Get llama-server URL for specified mode.

    Modes:
    - live: Fast responses (port 8080, qwen2.5:7b)
    - think: Deep reasoning (port 8082, deepseek-r1:7b)
    - deep: Background analysis (port 8082, deepseek-r1:7b)
    - code: Code generation (port 8081, qwen2.5-coder:7b)

    Args:
        mode: LLM mode (live/think/deep/code)

    Returns:
        llama-server URL
    """
    mode_ports = {
        "live": 8080,
        "think": 8082,
        "deep": 8082,
        "code": 8081
    }

    port = mode_ports.get(mode, 8080)
    return f"http://127.0.0.1:{port}"


def get_llama_model_path_for_mode(mode: str = "live") -> str:
    """
    Get model path for specified mode.

    Args:
        mode: LLM mode (live/think/deep/code)

    Returns:
        Path to GGUF model file
    """
    mode_models = {
        "live": "/home/kloros/models/gguf/qwen2.5-7b-instruct-q3_k_m.gguf",
        "think": "/home/kloros/models/gguf/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        "deep": "/home/kloros/models/gguf/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
        "code": "/home/kloros/models/gguf/qwen2.5-coder-7b-instruct-q4_k_m.gguf"
    }

    return mode_models.get(mode, mode_models["live"])


def check_llama_health(url: str) -> bool:
    """
    Check if llama-server is healthy.

    Compatible with both Ollama (/api/tags) and llama.cpp (/health).

    Args:
        url: Server URL to check

    Returns:
        True if server is responsive, False otherwise
    """
    import requests

    try:
        r = requests.get(f"{url}/health", timeout=2)
        if r.status_code == 200:
            status = r.json().get("status", "")
            if status == "ok":
                return True
    except Exception:
        pass

    try:
        r = requests.get(f"{url}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def get_llama_context_size(mode: str = "live") -> int:
    """
    Get context window size for llama-server mode.

    Note: This is informational only - context size is set at
    server startup via -c parameter, not per-request.

    Args:
        mode: LLM mode

    Returns:
        Context size in tokens
    """
    return 32768
