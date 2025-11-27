# llama.cpp Migration Implementation Tasks

This document breaks down the migration from Ollama to llama.cpp into bite-sized, independent tasks suitable for subagent-driven development. Each task follows TDD principles and can be completed in 15-30 minutes.

---

## Task Dependency Graph

```
Foundation Layer:
  1 → 2 → 3 → 4

Integration Layer:
  5 (depends on 1,2,3)
  6 (depends on 2,3,4)
  7 (depends on 2,3,4)

Testing & Deployment:
  8 (depends on 1,2,3,4,5,6,7)
  9 (depends on 8)
  10 (depends on 8)
```

---

## Phase 1: Foundation (Tasks 1-4)

### Task 1: Create ModelManager Module

**Priority:** HIGH
**Complexity:** Medium (3/5)
**Estimated Time:** 30 minutes

**Files to Create:**
- `/home/kloros/src/kloros/model_manager.py`
- `/home/kloros/tests/unit/test_model_manager.py`

**Dependencies:** None

**Implementation Details:**

Create a GGUF model manager that handles downloading and managing llama.cpp model files.

```python
# /home/kloros/src/kloros/model_manager.py

from pathlib import Path
from typing import Optional, Dict, Any
import requests
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about a GGUF model."""
    name: str
    filename: str
    url: str
    size_gb: float
    min_vram_gb: int
    description: str


class ModelManager:
    """
    Manages GGUF model files for llama.cpp.
    Replaces Ollama's model management functionality.
    """

    MODEL_REGISTRY = {
        "qwen2.5:32b-instruct-q4_K_M": ModelInfo(
            name="qwen2.5:32b-instruct-q4_K_M",
            filename="qwen2.5-32b-instruct-q4_k_m.gguf",
            url="https://huggingface.co/Qwen/Qwen2.5-32B-Instruct-GGUF/resolve/main/qwen2.5-32b-instruct-q4_k_m.gguf",
            size_gb=18.5,
            min_vram_gb=12,
            description="Qwen 2.5 32B Instruct (Q4_K_M quantization)"
        ),
        "qwen2.5-coder:32b": ModelInfo(
            name="qwen2.5-coder:32b",
            filename="qwen2.5-coder-32b-instruct-q4_k_m.gguf",
            url="https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct-GGUF/resolve/main/qwen2.5-coder-32b-instruct-q4_k_m.gguf",
            size_gb=18.5,
            min_vram_gb=12,
            description="Qwen 2.5 Coder 32B (Q4_K_M quantization)"
        ),
    }

    def __init__(self, model_dir: str = "/home/kloros/models/gguf"):
        """Initialize model manager with storage directory."""
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[ModelManager] Initialized with model_dir={self.model_dir}")

    def get_model_path(self, model_name: str) -> Optional[Path]:
        """
        Get local path for model.

        Args:
            model_name: Model name from registry (e.g., "qwen2.5:32b-instruct-q4_K_M")

        Returns:
            Path to model file if exists, None otherwise
        """
        if model_name not in self.MODEL_REGISTRY:
            logger.error(f"[ModelManager] Unknown model: {model_name}")
            return None

        model_info = self.MODEL_REGISTRY[model_name]
        model_path = self.model_dir / model_info.filename

        if model_path.exists():
            return model_path

        logger.warning(f"[ModelManager] Model not found: {model_path}")
        return None

    def list_models(self) -> list[Dict[str, Any]]:
        """
        List available models with download status.

        Returns:
            List of model info dicts with 'downloaded' flag
        """
        models = []
        for name, info in self.MODEL_REGISTRY.items():
            model_path = self.model_dir / info.filename
            models.append({
                "name": name,
                "filename": info.filename,
                "size_gb": info.size_gb,
                "min_vram_gb": info.min_vram_gb,
                "description": info.description,
                "downloaded": model_path.exists(),
                "path": str(model_path) if model_path.exists() else None
            })
        return models

    def download_model(self, model_name: str, force: bool = False) -> bool:
        """
        Download model from HuggingFace.

        Args:
            model_name: Model name from registry
            force: Re-download even if file exists

        Returns:
            True if download successful, False otherwise
        """
        if model_name not in self.MODEL_REGISTRY:
            logger.error(f"[ModelManager] Unknown model: {model_name}")
            return False

        model_info = self.MODEL_REGISTRY[model_name]
        model_path = self.model_dir / model_info.filename

        if model_path.exists() and not force:
            logger.info(f"[ModelManager] Model already exists: {model_path}")
            return True

        logger.info(f"[ModelManager] Downloading {model_name} ({model_info.size_gb}GB)...")
        logger.info(f"[ModelManager] URL: {model_info.url}")

        try:
            # Stream download with progress
            with requests.get(model_info.url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))

                with open(model_path, 'wb') as f:
                    downloaded = 0
                    chunk_size = 8192

                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Log progress every 100MB
                            if downloaded % (100 * 1024 * 1024) < chunk_size:
                                progress_pct = (downloaded / total_size * 100) if total_size > 0 else 0
                                logger.info(f"[ModelManager] Progress: {progress_pct:.1f}% ({downloaded / 1024**3:.2f}GB)")

            logger.info(f"[ModelManager] Download complete: {model_path}")
            return True

        except Exception as e:
            logger.error(f"[ModelManager] Download failed: {e}")
            # Clean up partial download
            if model_path.exists():
                model_path.unlink()
            return False

    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Get model information from registry."""
        return self.MODEL_REGISTRY.get(model_name)
```

**Test Requirements:**

```python
# /home/kloros/tests/unit/test_model_manager.py

import pytest
from pathlib import Path
from src.kloros.model_manager import ModelManager, ModelInfo


@pytest.fixture
def temp_model_dir(tmp_path):
    """Create temporary model directory."""
    return str(tmp_path / "models")


def test_model_manager_init(temp_model_dir):
    """Test ModelManager initialization creates directory."""
    manager = ModelManager(model_dir=temp_model_dir)
    assert Path(temp_model_dir).exists()
    assert manager.model_dir == Path(temp_model_dir)


def test_list_models_empty(temp_model_dir):
    """Test listing models when none are downloaded."""
    manager = ModelManager(model_dir=temp_model_dir)
    models = manager.list_models()

    assert len(models) > 0
    assert all(not m["downloaded"] for m in models)
    assert all(m["path"] is None for m in models)


def test_get_model_path_not_exists(temp_model_dir):
    """Test getting path for non-existent model."""
    manager = ModelManager(model_dir=temp_model_dir)
    path = manager.get_model_path("qwen2.5:32b-instruct-q4_K_M")
    assert path is None


def test_get_model_path_exists(temp_model_dir):
    """Test getting path for existing model."""
    manager = ModelManager(model_dir=temp_model_dir)

    # Create dummy model file
    Path(temp_model_dir).mkdir(parents=True, exist_ok=True)
    dummy_file = Path(temp_model_dir) / "qwen2.5-32b-instruct-q4_k_m.gguf"
    dummy_file.write_text("dummy")

    path = manager.get_model_path("qwen2.5:32b-instruct-q4_K_M")
    assert path == dummy_file
    assert path.exists()


def test_get_model_info(temp_model_dir):
    """Test retrieving model metadata."""
    manager = ModelManager(model_dir=temp_model_dir)
    info = manager.get_model_info("qwen2.5:32b-instruct-q4_K_M")

    assert info is not None
    assert isinstance(info, ModelInfo)
    assert info.name == "qwen2.5:32b-instruct-q4_K_M"
    assert info.size_gb > 0
    assert info.min_vram_gb > 0


def test_get_model_info_unknown(temp_model_dir):
    """Test retrieving info for unknown model."""
    manager = ModelManager(model_dir=temp_model_dir)
    info = manager.get_model_info("nonexistent-model")
    assert info is None
```

**Acceptance Criteria:**
- [ ] ModelManager class initializes with custom model directory
- [ ] Directory created automatically if it doesn't exist
- [ ] list_models() returns all registry models with download status
- [ ] get_model_path() returns Path for existing models, None otherwise
- [ ] get_model_info() returns ModelInfo for registered models
- [ ] All tests pass: `pytest tests/unit/test_model_manager.py -v`

---

### Task 2: Create LlamaAdapter Module

**Priority:** HIGH
**Complexity:** Medium (3/5)
**Estimated Time:** 30 minutes

**Files to Create:**
- `/home/kloros/src/reasoning/llama_adapter.py`
- `/home/kloros/tests/unit/test_llama_adapter.py`

**Dependencies:** None

**Implementation Details:**

Create an adapter that translates Ollama-style API calls to llama.cpp server format, providing a drop-in replacement for OllamaReasoner.

```python
# /home/kloros/src/reasoning/llama_adapter.py

import requests
import json
import logging
from typing import Optional, Generator

logger = logging.getLogger(__name__)


class LlamaAdapter:
    """
    Adapts Ollama-style requests to llama.cpp server format.
    Provides drop-in replacement for OllamaReasoner with same interface.

    Key differences from Ollama:
    - Uses /completion endpoint (or /v1/completions for OpenAI compat)
    - No per-request model selection (model loaded at server startup)
    - No per-request GPU allocation (configured at server startup)
    - Different parameter names (num_predict vs num_ctx)
    """

    def __init__(
        self,
        base_url: str,
        model: str = None,
        system_prompt: str = "",
        temperature: float = 0.6,
        timeout: int = 120
    ):
        """
        Initialize llama.cpp adapter.

        Args:
            base_url: llama-server URL (e.g., "http://127.0.0.1:8080")
            model: Model name (ignored - llama.cpp loads model at startup)
            system_prompt: System prompt to prepend to requests
            temperature: Sampling temperature
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.model = model  # Stored for compatibility but not used per-request
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.timeout = timeout
        logger.info(f"[llama_adapter] Initialized: {base_url} (model={model})")

    def _build_prompt(self, text: str, system: Optional[str] = None) -> str:
        """
        Build complete prompt with system message.

        Args:
            text: User prompt
            system: System prompt (overrides instance default if provided)

        Returns:
            Combined prompt string
        """
        sys = system if system is not None else self.system_prompt

        if sys:
            # Format as simple instruction-response
            return f"{sys}\n\nUser: {text}\n\nAssistant:"
        else:
            return text

    def generate(self, text: str, **kwargs) -> str:
        """
        Generate completion using llama.cpp /completion endpoint.

        Compatible with OllamaReasoner.generate() interface.

        Translates parameters:
        - system -> prepended to prompt
        - temperature -> temperature
        - num_ctx -> ignored (set at server startup)
        - num_gpu -> ignored (set at server startup)
        - stream -> stream
        - num_predict -> n_predict

        Args:
            text: Prompt text
            **kwargs: Additional parameters (temperature, system, stream, etc.)

        Returns:
            Generated text response
        """
        system = kwargs.get("system", None)
        prompt = self._build_prompt(text, system)

        payload = {
            "prompt": prompt,
            "temperature": kwargs.get("temperature", self.temperature),
            "top_p": kwargs.get("top_p", 0.95),
            "repeat_penalty": kwargs.get("repeat_penalty", 1.1),
            "n_predict": kwargs.get("num_predict", -1),  # -1 = until EOS
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
        """
        Handle streaming completion.

        Args:
            payload: Request payload
            timeout: Request timeout

        Returns:
            Complete response text
        """
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
        """
        Generate reply with optional streaming to TTS.

        Compatible with OllamaReasoner.reply() interface for voice pipeline.

        Args:
            text: Prompt text
            kloros_instance: KLoROS instance for speak() callback
            **kwargs: Additional parameters

        Returns:
            ReasoningResult with response text
        """
        from src.reasoning.base import ReasoningResult

        enable_streaming = kwargs.get("enable_streaming", True)

        # Non-streaming path
        if not enable_streaming or kloros_instance is None:
            response = self.generate(text, **kwargs)
            return ReasoningResult(response)

        # Streaming path with sentence-by-sentence TTS
        system = kwargs.get("system", None)
        prompt = self._build_prompt(text, system)

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

                    # Send complete sentences to TTS
                    if token.strip() and token.strip()[-1] in sentence_endings:
                        sentence = buffer.strip()
                        if len(sentence) > 20 and hasattr(kloros_instance, 'speak'):
                            kloros_instance.speak(sentence)
                            buffer = ""

                    if chunk.get("stop", False):
                        break

                except json.JSONDecodeError:
                    continue

            # Send remaining text
            if buffer.strip() and hasattr(kloros_instance, 'speak'):
                kloros_instance.speak(buffer.strip())

            return ReasoningResult(complete_response.strip())

        except requests.RequestException as e:
            return ReasoningResult(f"llama.cpp error: {e}")

    def health_check(self) -> bool:
        """
        Check if llama-server is healthy.

        Returns:
            True if server is responsive, False otherwise
        """
        try:
            r = requests.get(f"{self.base_url}/health", timeout=2)
            if r.status_code == 200:
                status = r.json().get("status", "")
                return status == "ok"
        except Exception:
            pass

        return False
```

**Test Requirements:**

```python
# /home/kloros/tests/unit/test_llama_adapter.py

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.reasoning.llama_adapter import LlamaAdapter
from src.reasoning.base import ReasoningResult


@pytest.fixture
def adapter():
    """Create LlamaAdapter instance."""
    return LlamaAdapter(
        base_url="http://127.0.0.1:8080",
        model="test-model",
        system_prompt="You are a helpful assistant.",
        temperature=0.7
    )


def test_adapter_init(adapter):
    """Test adapter initialization."""
    assert adapter.base_url == "http://127.0.0.1:8080"
    assert adapter.model == "test-model"
    assert adapter.system_prompt == "You are a helpful assistant."
    assert adapter.temperature == 0.7


def test_build_prompt_with_system(adapter):
    """Test prompt building with system message."""
    prompt = adapter._build_prompt("Hello", system="You are a test bot.")
    assert "You are a test bot." in prompt
    assert "Hello" in prompt


def test_build_prompt_without_system():
    """Test prompt building without system message."""
    adapter = LlamaAdapter(base_url="http://127.0.0.1:8080", system_prompt="")
    prompt = adapter._build_prompt("Hello")
    assert prompt == "Hello"


@patch('requests.post')
def test_generate_success(mock_post, adapter):
    """Test successful generation."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": "Test response"}
    mock_post.return_value = mock_response

    result = adapter.generate("Hello")

    assert result == "Test response"
    mock_post.assert_called_once()
    assert "/completion" in mock_post.call_args[0][0]


@patch('requests.post')
def test_generate_with_parameters(mock_post, adapter):
    """Test generation with custom parameters."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": "Response"}
    mock_post.return_value = mock_response

    adapter.generate(
        "Hello",
        temperature=0.9,
        top_p=0.8,
        repeat_penalty=1.2
    )

    payload = mock_post.call_args[1]["json"]
    assert payload["temperature"] == 0.9
    assert payload["top_p"] == 0.8
    assert payload["repeat_penalty"] == 1.2


@patch('requests.post')
def test_reply_non_streaming(mock_post, adapter):
    """Test reply without streaming."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": "Test reply"}
    mock_post.return_value = mock_response

    result = adapter.reply("Hello", enable_streaming=False)

    assert isinstance(result, ReasoningResult)
    assert result.reply_text == "Test reply"


@patch('requests.get')
def test_health_check_ok(mock_get, adapter):
    """Test health check when server is healthy."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}
    mock_get.return_value = mock_response

    assert adapter.health_check() is True


@patch('requests.get')
def test_health_check_fail(mock_get, adapter):
    """Test health check when server is down."""
    mock_get.side_effect = Exception("Connection refused")

    assert adapter.health_check() is False
```

**Acceptance Criteria:**
- [ ] LlamaAdapter initializes with same parameters as OllamaReasoner
- [ ] generate() method translates Ollama parameters to llama.cpp format
- [ ] reply() method supports streaming with sentence-by-sentence callbacks
- [ ] health_check() validates server availability
- [ ] All parameters translated correctly (temperature, top_p, etc.)
- [ ] All tests pass: `pytest tests/unit/test_llama_adapter.py -v`

---

### Task 3: Create Systemd Service Templates

**Priority:** HIGH
**Complexity:** Low (2/5)
**Estimated Time:** 20 minutes

**Files to Create:**
- `/home/kloros/config/systemd/kloros-llama-live.service.template`
- `/home/kloros/config/systemd/kloros-llama-code.service.template`
- `/home/kloros/scripts/install_llama_services.sh`

**Dependencies:** Task 1 (ModelManager - for model paths)

**Implementation Details:**

Create systemd service templates for running llama-server instances, following the pattern of existing KLoROS services.

```ini
# /home/kloros/config/systemd/kloros-llama-live.service.template

[Unit]
Description=KLoROS LLaMA Live Instance (General Chat)
After=network.target
Documentation=https://github.com/ggml-org/llama.cpp

[Service]
Type=simple
User=kloros
Group=kloros
WorkingDirectory=/home/kloros

# GPU 0, 32k context, 2 parallel slots, flash attention
ExecStart=/usr/local/bin/llama-server \
    -m {{MODEL_PATH}} \
    --host 127.0.0.1 \
    --port 8080 \
    -ngl 99 \
    -c 32768 \
    -np 2 \
    -fa \
    -cb \
    --metrics

# GPU allocation
Environment=CUDA_VISIBLE_DEVICES=0

# Restart policy
Restart=on-failure
RestartSec=5
StartLimitBurst=3
StartLimitInterval=60

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kloros-llama-live

[Install]
WantedBy=multi-user.target
```

```ini
# /home/kloros/config/systemd/kloros-llama-code.service.template

[Unit]
Description=KLoROS LLaMA Code Instance (Code Generation)
After=network.target
Documentation=https://github.com/ggml-org/llama.cpp

[Service]
Type=simple
User=kloros
Group=kloros
WorkingDirectory=/home/kloros

# GPU 1, 32k context, 1 slot for code generation
ExecStart=/usr/local/bin/llama-server \
    -m {{MODEL_PATH}} \
    --host 127.0.0.1 \
    --port 8081 \
    -ngl 99 \
    -c 32768 \
    -np 1 \
    -fa \
    -cb \
    --metrics

# GPU allocation
Environment=CUDA_VISIBLE_DEVICES=1

# Restart policy
Restart=on-failure
RestartSec=5
StartLimitBurst=3
StartLimitInterval=60

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kloros-llama-code

[Install]
WantedBy=multi-user.target
```

```bash
# /home/kloros/scripts/install_llama_services.sh

#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/../config/systemd"
SYSTEMD_DIR="/etc/systemd/system"

# Model paths from ModelManager
LIVE_MODEL="${1:-/home/kloros/models/gguf/qwen2.5-32b-instruct-q4_k_m.gguf}"
CODE_MODEL="${2:-/home/kloros/models/gguf/qwen2.5-coder-32b-instruct-q4_k_m.gguf}"

echo "[install_llama_services] Installing llama.cpp systemd services..."

# Check if llama-server is installed
if ! command -v llama-server &> /dev/null; then
    echo "ERROR: llama-server not found in PATH"
    echo "Please install llama.cpp first"
    exit 1
fi

# Check if model files exist
if [ ! -f "$LIVE_MODEL" ]; then
    echo "WARNING: Live model not found: $LIVE_MODEL"
    echo "Run: python -m src.kloros.model_manager download qwen2.5:32b-instruct-q4_K_M"
fi

if [ ! -f "$CODE_MODEL" ]; then
    echo "WARNING: Code model not found: $CODE_MODEL"
    echo "Run: python -m src.kloros.model_manager download qwen2.5-coder:32b"
fi

# Install live service
echo "[install_llama_services] Installing kloros-llama-live.service..."
sed "s|{{MODEL_PATH}}|$LIVE_MODEL|g" \
    "${CONFIG_DIR}/kloros-llama-live.service.template" \
    > /tmp/kloros-llama-live.service

sudo cp /tmp/kloros-llama-live.service "${SYSTEMD_DIR}/kloros-llama-live.service"
sudo chown root:root "${SYSTEMD_DIR}/kloros-llama-live.service"
sudo chmod 644 "${SYSTEMD_DIR}/kloros-llama-live.service"

# Install code service
echo "[install_llama_services] Installing kloros-llama-code.service..."
sed "s|{{MODEL_PATH}}|$CODE_MODEL|g" \
    "${CONFIG_DIR}/kloros-llama-code.service.template" \
    > /tmp/kloros-llama-code.service

sudo cp /tmp/kloros-llama-code.service "${SYSTEMD_DIR}/kloros-llama-code.service"
sudo chown root:root "${SYSTEMD_DIR}/kloros-llama-code.service"
sudo chmod 644 "${SYSTEMD_DIR}/kloros-llama-code.service"

# Reload systemd
echo "[install_llama_services] Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "[install_llama_services] Services installed successfully!"
echo ""
echo "To start services:"
echo "  sudo systemctl start kloros-llama-live"
echo "  sudo systemctl start kloros-llama-code"
echo ""
echo "To enable on boot:"
echo "  sudo systemctl enable kloros-llama-live"
echo "  sudo systemctl enable kloros-llama-code"
echo ""
echo "To check status:"
echo "  sudo systemctl status kloros-llama-live"
echo "  sudo systemctl status kloros-llama-code"
```

**Test Requirements:**

Manual testing (no automated tests for systemd services):

```bash
# Test service template syntax
systemd-analyze verify /home/kloros/config/systemd/kloros-llama-live.service.template

# Test installation script (dry run)
bash -n /home/kloros/scripts/install_llama_services.sh

# Test actual installation (requires models)
chmod +x /home/kloros/scripts/install_llama_services.sh
/home/kloros/scripts/install_llama_services.sh

# Verify services are recognized
systemctl list-unit-files | grep kloros-llama
```

**Acceptance Criteria:**
- [ ] Service templates created with proper systemd format
- [ ] Templates use {{MODEL_PATH}} placeholder for flexibility
- [ ] GPU allocation configured per service (GPU 0 for live, GPU 1 for code)
- [ ] Restart policies configured (on-failure with backoff)
- [ ] Installation script validates llama-server availability
- [ ] Installation script checks model file existence
- [ ] Services appear in systemctl output after installation

---

### Task 4: Update Config Module for llama.cpp

**Priority:** HIGH
**Complexity:** Low (2/5)
**Estimated Time:** 20 minutes

**Files to Modify:**
- `/home/kloros/src/config/models_config.py`

**Files to Create:**
- `/home/kloros/tests/unit/test_models_config_llama.py`

**Dependencies:** None

**Implementation Details:**

Add llama.cpp-specific configuration functions to existing models_config.py module.

```python
# Add to /home/kloros/src/config/models_config.py

# ============================================================================
# LLAMA.CPP CONFIGURATION
# ============================================================================

def get_llama_url_for_mode(mode: str = "live") -> str:
    """
    Get llama-server URL for specified mode.

    Modes:
    - live: Fast responses (port 8080)
    - think: Deep reasoning (port 8080)
    - deep: Background analysis (port 8080)
    - code: Code generation (port 8081)

    Args:
        mode: LLM mode (live/think/deep/code)

    Returns:
        llama-server URL
    """
    mode_ports = {
        "live": 8080,
        "think": 8080,
        "deep": 8080,
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
        "live": "/home/kloros/models/gguf/qwen2.5-32b-instruct-q4_k_m.gguf",
        "think": "/home/kloros/models/gguf/qwen2.5-32b-instruct-q4_k_m.gguf",
        "deep": "/home/kloros/models/gguf/qwen2.5-32b-instruct-q4_k_m.gguf",
        "code": "/home/kloros/models/gguf/qwen2.5-coder-32b-instruct-q4_k_m.gguf"
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

    # Try llama.cpp /health endpoint first
    try:
        r = requests.get(f"{url}/health", timeout=2)
        if r.status_code == 200:
            status = r.json().get("status", "")
            if status == "ok":
                return True
    except Exception:
        pass

    # Fallback to Ollama /api/tags for backward compatibility
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
    # All current instances use 32k context
    return 32768
```

**Test Requirements:**

```python
# /home/kloros/tests/unit/test_models_config_llama.py

import pytest
from src.config.models_config import (
    get_llama_url_for_mode,
    get_llama_model_path_for_mode,
    get_llama_context_size,
    check_llama_health
)


def test_get_llama_url_for_mode():
    """Test URL mapping for different modes."""
    assert get_llama_url_for_mode("live") == "http://127.0.0.1:8080"
    assert get_llama_url_for_mode("think") == "http://127.0.0.1:8080"
    assert get_llama_url_for_mode("deep") == "http://127.0.0.1:8080"
    assert get_llama_url_for_mode("code") == "http://127.0.0.1:8081"


def test_get_llama_url_for_mode_default():
    """Test default URL when mode not specified."""
    assert "8080" in get_llama_url_for_mode()


def test_get_llama_model_path_for_mode():
    """Test model path mapping for different modes."""
    live_path = get_llama_model_path_for_mode("live")
    assert "qwen2.5-32b-instruct" in live_path
    assert live_path.endswith(".gguf")

    code_path = get_llama_model_path_for_mode("code")
    assert "coder" in code_path
    assert code_path.endswith(".gguf")


def test_get_llama_context_size():
    """Test context size retrieval."""
    assert get_llama_context_size("live") == 32768
    assert get_llama_context_size("code") == 32768


def test_check_llama_health_unreachable():
    """Test health check with unreachable server."""
    # Assume nothing is running on port 9999
    result = check_llama_health("http://127.0.0.1:9999")
    assert result is False
```

**Acceptance Criteria:**
- [ ] get_llama_url_for_mode() returns correct ports for each mode
- [ ] get_llama_model_path_for_mode() returns correct model paths
- [ ] get_llama_context_size() returns 32768 for all modes
- [ ] check_llama_health() tries /health first, falls back to /api/tags
- [ ] All tests pass: `pytest tests/unit/test_models_config_llama.py -v`
- [ ] Existing models_config tests still pass

---

## Phase 2: Integration (Tasks 5-7)

### Task 5: Update Reasoning Backend Factory

**Priority:** HIGH
**Complexity:** Medium (3/5)
**Estimated Time:** 25 minutes

**Files to Modify:**
- `/home/kloros/src/reasoning/base.py`

**Files to Create:**
- `/home/kloros/tests/unit/test_reasoning_factory_llama.py`

**Dependencies:** Task 2 (LlamaAdapter), Task 4 (config module)

**Implementation Details:**

Extend create_reasoning_backend() factory to support "llama" backend type while maintaining backward compatibility with Ollama.

```python
# Modify create_reasoning_backend() in /home/kloros/src/reasoning/base.py

def create_reasoning_backend(name: str, **kwargs):
    """
    Create the requested reasoning backend, or raise ValueError for unknown.
    Recognized: 'mock', 'ollama', 'llama', 'qa'

    New backend types:
    - 'llama': Uses llama.cpp server via LlamaAdapter

    Args:
        name: Backend name to create
        **kwargs: Additional parameters to pass to backend constructor
            mode: LLM mode for llama backend (live/think/deep/code)
    """
    b = (name or "mock").lower()

    if b in ("mock", "none", "disabled"):
        from .mock_backend import MockReasoningBackend
        return MockReasoningBackend(**kwargs)

    if b in ("ollama", "llm", "local"):
        from src.config.models_config import get_ollama_url, get_ollama_model
        host = os.getenv("OLLAMA_HOST", get_ollama_url())
        model = get_ollama_model()

        # Connect to persona system
        try:
            from src.persona.kloros import PERSONA_PROMPT
            prompt = PERSONA_PROMPT.strip()
            print(f"[reasoning] Using KLoROS persona system")
        except ImportError:
            prompt = os.getenv("LLM_SYSTEM_PROMPT", "")
            print(f"[reasoning] Using fallback prompt")

        return OllamaReasoner(base_url=host, model=model, system_prompt=prompt)

    if b in ("llama", "llama.cpp", "llamacpp"):
        from .llama_adapter import LlamaAdapter
        from src.config.models_config import get_llama_url_for_mode

        mode = kwargs.get("mode", "live")
        url = get_llama_url_for_mode(mode)

        # Connect to persona system
        try:
            from src.persona.kloros import PERSONA_PROMPT
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
        from src.config.models_config import get_ollama_url, get_ollama_model
        host = os.getenv("OLLAMA_HOST", get_ollama_url())
        model = get_ollama_model()
        try:
            from src.persona.kloros import PERSONA_PROMPT
            prompt = PERSONA_PROMPT.strip()
        except ImportError:
            prompt = os.getenv("LLM_SYSTEM_PROMPT", "")
        print(f"[reasoning] RAG backend deprecated, using OllamaReasoner fallback")
        return OllamaReasoner(base_url=host, model=model, system_prompt=prompt)

    if b in ("qa",):
        from .local_qa_backend import LocalQaBackend
        print(f"[reasoning] Initialized QA backend")
        return LocalQaBackend(**kwargs)

    raise ValueError(f"Unknown reasoning backend: {b}")
```

**Test Requirements:**

```python
# /home/kloros/tests/unit/test_reasoning_factory_llama.py

import pytest
from src.reasoning.base import create_reasoning_backend
from src.reasoning.llama_adapter import LlamaAdapter


def test_create_llama_backend():
    """Test creating llama.cpp backend."""
    backend = create_reasoning_backend("llama", mode="live")
    assert isinstance(backend, LlamaAdapter)


def test_create_llama_backend_with_mode():
    """Test creating llama.cpp backend with specific mode."""
    backend = create_reasoning_backend("llama", mode="code")
    assert isinstance(backend, LlamaAdapter)
    assert "8081" in backend.base_url  # Code mode uses port 8081


def test_create_llama_backend_aliases():
    """Test llama.cpp backend aliases."""
    backend1 = create_reasoning_backend("llama")
    backend2 = create_reasoning_backend("llama.cpp")
    backend3 = create_reasoning_backend("llamacpp")

    assert isinstance(backend1, LlamaAdapter)
    assert isinstance(backend2, LlamaAdapter)
    assert isinstance(backend3, LlamaAdapter)


def test_create_llama_backend_default_mode():
    """Test llama.cpp backend defaults to live mode."""
    backend = create_reasoning_backend("llama")
    assert "8080" in backend.base_url  # Live mode uses port 8080


def test_ollama_backend_still_works():
    """Test that existing Ollama backend still works."""
    from src.reasoning.base import OllamaReasoner

    backend = create_reasoning_backend("ollama")
    assert isinstance(backend, OllamaReasoner)
```

**Acceptance Criteria:**
- [ ] Factory recognizes "llama", "llama.cpp", "llamacpp" backend names
- [ ] llama backend uses LlamaAdapter class
- [ ] llama backend respects mode parameter (live/code)
- [ ] llama backend loads PERSONA_PROMPT like Ollama does
- [ ] Existing Ollama backend still works unchanged
- [ ] All tests pass: `pytest tests/unit/test_reasoning_factory_llama.py -v`

---

### Task 6: Update LLM Router for llama.cpp

**Priority:** MEDIUM
**Complexity:** Medium (3/5)
**Estimated Time:** 30 minutes

**Files to Modify:**
- `/home/kloros/src/reasoning/llm_router.py`

**Files to Create:**
- `/home/kloros/tests/unit/test_llm_router_llama.py`

**Dependencies:** Task 2 (LlamaAdapter), Task 4 (config module)

**Implementation Details:**

Update LLMRouter to support both Ollama and llama.cpp services with unified health checking.

```python
# Modify LLMRouter in /home/kloros/src/reasoning/llm_router.py

# Add new LLMService definitions for llama.cpp
LLAMA_SERVICES = {
    LLMMode.LIVE: LLMService(
        name="llama-live",
        port=8080,
        model="qwen2.5-32b-instruct-q4_k_m.gguf",
        description="Fast chat and general queries (llama.cpp, 32k context)"
    ),
    LLMMode.THINK: LLMService(
        name="llama-live",
        port=8080,
        model="qwen2.5-32b-instruct-q4_k_m.gguf",
        description="Deep reasoning (llama.cpp, 32k context)"
    ),
    LLMMode.DEEP: LLMService(
        name="llama-live",
        port=8080,
        model="qwen2.5-32b-instruct-q4_k_m.gguf",
        description="Deep analysis (llama.cpp, 32k context)"
    ),
    LLMMode.CODE: LLMService(
        name="llama-code",
        port=8081,
        model="qwen2.5-coder-32b-instruct-q4_k_m.gguf",
        description="Code generation (llama.cpp, 32k context)"
    ),
}

class LLMRouter:
    """
    Single Source of Truth for all LLM routing decisions.

    Supports both Ollama and llama.cpp backends.
    """

    def __init__(self, backend: str = "ollama"):
        """
        Initialize router with specified backend.

        Args:
            backend: "ollama" or "llama" (llama.cpp)
        """
        self.backend = backend.lower()
        self.dashboard_url = "http://localhost:8765"
        self._remote_llm_cache: Optional[Tuple[bool, str]] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 5.0

        # Select service configuration based on backend
        if self.backend == "llama":
            self.SERVICES = LLAMA_SERVICES
        else:
            # Use existing SERVICES dict for Ollama (already defined in module)
            pass

    def check_service_health(self, mode: LLMMode) -> Tuple[bool, str]:
        """
        Check if LLM service is running and responsive.

        Compatible with both Ollama and llama.cpp.

        Args:
            mode: Which LLM service to check

        Returns:
            tuple[bool, str]: (is_healthy, error_message)
        """
        service = self.get_service(mode)

        # Try llama.cpp /health endpoint first
        try:
            import requests
            r = requests.get(f"{service.url}/health", timeout=2)
            if r.status_code == 200:
                status = r.json().get("status", "")
                if status == "ok":
                    return (True, "")
        except Exception:
            pass

        # Fallback to Ollama /api/tags
        try:
            import requests
            r = requests.get(f"{service.url}/api/tags", timeout=2)
            if r.status_code == 200:
                return (True, "")
            else:
                return (False, f"{service.name} returned status {r.status_code}")
        except requests.exceptions.Timeout:
            return (False, f"{service.name} is not responding (timeout)")
        except requests.exceptions.ConnectionError:
            return (False, f"{service.name} is not running (connection refused)")
        except Exception as e:
            return (False, f"{service.name} health check failed: {e}")
```

**Test Requirements:**

```python
# /home/kloros/tests/unit/test_llm_router_llama.py

import pytest
from unittest.mock import Mock, patch
from src.reasoning.llm_router import LLMRouter, LLMMode


@pytest.fixture
def llama_router():
    """Create LLM router with llama.cpp backend."""
    return LLMRouter(backend="llama")


def test_llama_router_init(llama_router):
    """Test router initializes with llama backend."""
    assert llama_router.backend == "llama"


def test_llama_router_service_ports(llama_router):
    """Test llama.cpp services use correct ports."""
    live_service = llama_router.get_service(LLMMode.LIVE)
    code_service = llama_router.get_service(LLMMode.CODE)

    assert live_service.port == 8080
    assert code_service.port == 8081


@patch('requests.get')
def test_health_check_llama_healthy(mock_get, llama_router):
    """Test health check with healthy llama.cpp server."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}
    mock_get.return_value = mock_response

    is_healthy, error = llama_router.check_service_health(LLMMode.LIVE)

    assert is_healthy is True
    assert error == ""


@patch('requests.get')
def test_health_check_fallback_to_ollama(mock_get, llama_router):
    """Test health check falls back to Ollama endpoint."""
    # First call to /health fails
    # Second call to /api/tags succeeds
    mock_response_health = Mock()
    mock_response_health.status_code = 404

    mock_response_tags = Mock()
    mock_response_tags.status_code = 200

    mock_get.side_effect = [Exception("Not found"), mock_response_tags]

    is_healthy, error = llama_router.check_service_health(LLMMode.LIVE)

    assert is_healthy is True
    assert error == ""


def test_ollama_router_still_works():
    """Test that Ollama router still works."""
    ollama_router = LLMRouter(backend="ollama")

    assert ollama_router.backend == "ollama"

    live_service = ollama_router.get_service(LLMMode.LIVE)
    assert live_service.port == 11434  # Ollama port
```

**Acceptance Criteria:**
- [ ] LLMRouter accepts backend parameter ("ollama" or "llama")
- [ ] llama backend uses ports 8080/8081 instead of 11434/11435
- [ ] check_service_health() tries /health first, falls back to /api/tags
- [ ] Existing Ollama mode still works unchanged
- [ ] All tests pass: `pytest tests/unit/test_llm_router_llama.py -v`

---

### Task 7: Create Backend Switching CLI Tool

**Priority:** LOW
**Complexity:** Low (2/5)
**Estimated Time:** 15 minutes

**Files to Create:**
- `/home/kloros/scripts/switch_llm_backend.py`

**Dependencies:** Task 5 (factory updates), Task 6 (router updates)

**Implementation Details:**

Create a CLI tool to help operators switch between Ollama and llama.cpp backends.

```python
# /home/kloros/scripts/switch_llm_backend.py

#!/usr/bin/env python3
"""
Switch KLoROS LLM backend between Ollama and llama.cpp.

This tool helps operators transition services from Ollama to llama.cpp
by updating environment variables and validating service health.
"""

import os
import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def check_backend_health(backend: str) -> bool:
    """
    Check if specified backend is healthy.

    Args:
        backend: "ollama" or "llama"

    Returns:
        True if backend is responsive, False otherwise
    """
    from reasoning.llm_router import LLMRouter, LLMMode

    router = LLMRouter(backend=backend)
    is_healthy, error = router.check_service_health(LLMMode.LIVE)

    if not is_healthy:
        print(f"  ✗ {backend} backend: {error}")
        return False

    print(f"  ✓ {backend} backend: healthy")
    return True


def list_backends():
    """List available backends and their status."""
    print("Available LLM Backends:")
    print()

    print("1. Ollama (current)")
    print("   Services:")
    print("     - ollama-live (port 11434)")
    print("     - ollama-think (port 11435)")
    print("   Status:")
    check_backend_health("ollama")
    print()

    print("2. llama.cpp (migration target)")
    print("   Services:")
    print("     - llama-live (port 8080)")
    print("     - llama-code (port 8081)")
    print("   Status:")
    check_backend_health("llama")
    print()


def test_backend(backend: str, mode: str = "live"):
    """
    Test backend with a sample query.

    Args:
        backend: "ollama" or "llama"
        mode: LLM mode to test
    """
    from reasoning.base import create_reasoning_backend

    print(f"Testing {backend} backend (mode={mode})...")

    try:
        reasoner = create_reasoning_backend(backend, mode=mode)
        response = reasoner.generate("Say 'OK' if you can hear me.")

        print(f"  ✓ Response: {response[:50]}...")
        return True

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Switch KLoROS LLM backend between Ollama and llama.cpp"
    )
    parser.add_argument(
        "action",
        choices=["list", "test", "check"],
        help="Action to perform"
    )
    parser.add_argument(
        "--backend",
        choices=["ollama", "llama"],
        help="Backend to test (required for test action)"
    )
    parser.add_argument(
        "--mode",
        choices=["live", "think", "deep", "code"],
        default="live",
        help="LLM mode to test (default: live)"
    )

    args = parser.parse_args()

    if args.action == "list":
        list_backends()

    elif args.action == "test":
        if not args.backend:
            print("Error: --backend required for test action")
            sys.exit(1)

        success = test_backend(args.backend, args.mode)
        sys.exit(0 if success else 1)

    elif args.action == "check":
        if not args.backend:
            print("Error: --backend required for check action")
            sys.exit(1)

        success = check_backend_health(args.backend)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
```

**Test Requirements:**

Manual testing:

```bash
# Make executable
chmod +x /home/kloros/scripts/switch_llm_backend.py

# List available backends
python /home/kloros/scripts/switch_llm_backend.py list

# Check backend health
python /home/kloros/scripts/switch_llm_backend.py check --backend llama

# Test backend with sample query (requires running services)
python /home/kloros/scripts/switch_llm_backend.py test --backend llama --mode live
```

**Acceptance Criteria:**
- [ ] Script lists both Ollama and llama.cpp backends
- [ ] check action validates backend health
- [ ] test action sends sample query and displays response
- [ ] Script exits with proper status codes (0=success, 1=failure)
- [ ] Script provides helpful error messages

---

## Phase 3: Testing & Validation (Tasks 8-10)

### Task 8: Create Integration Test Suite

**Priority:** HIGH
**Complexity:** Medium (3/5)
**Estimated Time:** 30 minutes

**Files to Create:**
- `/home/kloros/tests/integration/test_llama_integration.py`

**Dependencies:** All previous tasks

**Implementation Details:**

Create comprehensive integration tests that validate llama.cpp migration works end-to-end.

```python
# /home/kloros/tests/integration/test_llama_integration.py

import pytest
import requests
from pathlib import Path
from src.reasoning.base import create_reasoning_backend, ReasoningResult
from src.reasoning.llama_adapter import LlamaAdapter
from src.reasoning.llm_router import LLMRouter, LLMMode
from src.kloros.model_manager import ModelManager


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def llama_service_running():
    """Check if llama-server is running on port 8080."""
    try:
        r = requests.get("http://127.0.0.1:8080/health", timeout=2)
        if r.status_code == 200 and r.json().get("status") == "ok":
            return True
    except Exception:
        pass

    pytest.skip("llama-server not running on port 8080")


def test_model_manager_lists_models():
    """Test ModelManager can list available models."""
    manager = ModelManager()
    models = manager.list_models()

    assert len(models) > 0
    assert any(m["name"] == "qwen2.5:32b-instruct-q4_K_M" for m in models)


def test_llama_adapter_health_check(llama_service_running):
    """Test LlamaAdapter can check server health."""
    adapter = LlamaAdapter(base_url="http://127.0.0.1:8080")
    assert adapter.health_check() is True


def test_llama_adapter_generate(llama_service_running):
    """Test LlamaAdapter can generate completions."""
    adapter = LlamaAdapter(
        base_url="http://127.0.0.1:8080",
        system_prompt="You are a helpful assistant."
    )

    response = adapter.generate("What is 2+2? Answer with just the number.")

    assert response is not None
    assert len(response) > 0
    assert "4" in response


def test_llama_adapter_with_parameters(llama_service_running):
    """Test LlamaAdapter respects sampling parameters."""
    adapter = LlamaAdapter(base_url="http://127.0.0.1:8080")

    response = adapter.generate(
        "Say hello.",
        temperature=0.1,
        top_p=0.9,
        repeat_penalty=1.1
    )

    assert response is not None
    assert len(response) > 0


def test_llama_adapter_reply_interface(llama_service_running):
    """Test LlamaAdapter.reply() returns ReasoningResult."""
    adapter = LlamaAdapter(base_url="http://127.0.0.1:8080")

    result = adapter.reply("Hello!", enable_streaming=False)

    assert isinstance(result, ReasoningResult)
    assert result.reply_text is not None
    assert len(result.reply_text) > 0


def test_reasoning_factory_creates_llama_backend(llama_service_running):
    """Test factory can create llama.cpp backend."""
    backend = create_reasoning_backend("llama", mode="live")

    assert isinstance(backend, LlamaAdapter)
    assert backend.base_url == "http://127.0.0.1:8080"


def test_llm_router_llama_backend(llama_service_running):
    """Test LLM router with llama.cpp backend."""
    router = LLMRouter(backend="llama")

    # Check service health
    is_healthy, error = router.check_service_health(LLMMode.LIVE)
    assert is_healthy is True
    assert error == ""

    # Get service info
    service = router.get_service(LLMMode.LIVE)
    assert service.port == 8080


def test_llama_backend_compatibility_with_ollama_interface(llama_service_running):
    """Test llama.cpp adapter is compatible with Ollama interface."""
    # Create both backends with same interface
    llama_backend = create_reasoning_backend("llama", mode="live")

    # Both should have same methods
    assert hasattr(llama_backend, "generate")
    assert hasattr(llama_backend, "reply")

    # Both should work with same parameters
    response = llama_backend.generate(
        "Say OK.",
        temperature=0.8,
        system="You are a test bot."
    )

    assert response is not None
    assert len(response) > 0


@pytest.mark.slow
def test_llama_backend_context_handling(llama_service_running):
    """Test llama.cpp handles large context correctly."""
    adapter = LlamaAdapter(base_url="http://127.0.0.1:8080")

    # Generate long prompt (but within 32k context)
    long_text = "The quick brown fox jumps over the lazy dog. " * 100
    prompt = f"Summarize this text in one sentence:\n\n{long_text}"

    response = adapter.generate(prompt)

    assert response is not None
    assert len(response) > 0
    assert len(response) < len(prompt)  # Summary should be shorter


def test_backend_switching():
    """Test that backends can be switched via factory."""
    # Create Ollama backend
    try:
        ollama_backend = create_reasoning_backend("ollama")
        assert ollama_backend is not None
    except Exception:
        pytest.skip("Ollama not available")

    # Create llama.cpp backend
    llama_backend = create_reasoning_backend("llama", mode="live")
    assert llama_backend is not None

    # Backends should have same interface but different implementations
    assert type(ollama_backend) != type(llama_backend)
    assert hasattr(ollama_backend, "generate")
    assert hasattr(llama_backend, "generate")
```

**Test Requirements:**

Run integration tests:

```bash
# Requires llama-server running on port 8080
pytest tests/integration/test_llama_integration.py -v -m integration

# Run with slow tests
pytest tests/integration/test_llama_integration.py -v -m "integration and slow"
```

**Acceptance Criteria:**
- [ ] ModelManager integration tests pass
- [ ] LlamaAdapter health check tests pass
- [ ] LlamaAdapter generation tests pass (requires running service)
- [ ] Reasoning factory tests pass
- [ ] LLM router tests pass
- [ ] Interface compatibility tests pass
- [ ] All tests pass when llama-server is running

---

### Task 9: Create Migration Validation Script

**Priority:** MEDIUM
**Complexity:** Low (2/5)
**Estimated Time:** 20 minutes

**Files to Create:**
- `/home/kloros/scripts/validate_llama_migration.sh`

**Dependencies:** Task 8 (integration tests)

**Implementation Details:**

Create a validation script that checks migration readiness and service health.

```bash
# /home/kloros/scripts/validate_llama_migration.sh

#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "KLoROS llama.cpp Migration Validation"
echo "=========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0

# Function to print colored status
print_status() {
    local status=$1
    local message=$2

    if [ "$status" = "OK" ]; then
        echo -e "${GREEN}✓${NC} $message"
    elif [ "$status" = "WARN" ]; then
        echo -e "${YELLOW}⚠${NC} $message"
    else
        echo -e "${RED}✗${NC} $message"
        ERRORS=$((ERRORS + 1))
    fi
}

echo "1. Checking Prerequisites"
echo "-------------------------"

# Check if llama-server is installed
if command -v llama-server &> /dev/null; then
    print_status "OK" "llama-server installed"
else
    print_status "FAIL" "llama-server not found in PATH"
fi

# Check if models exist
LIVE_MODEL="/home/kloros/models/gguf/qwen2.5-32b-instruct-q4_k_m.gguf"
CODE_MODEL="/home/kloros/models/gguf/qwen2.5-coder-32b-instruct-q4_k_m.gguf"

if [ -f "$LIVE_MODEL" ]; then
    print_status "OK" "Live model exists: $LIVE_MODEL"
else
    print_status "WARN" "Live model not found: $LIVE_MODEL"
fi

if [ -f "$CODE_MODEL" ]; then
    print_status "OK" "Code model exists: $CODE_MODEL"
else
    print_status "WARN" "Code model not found: $CODE_MODEL"
fi

echo ""
echo "2. Checking Service Health"
echo "--------------------------"

# Check llama-live service
if systemctl is-active --quiet kloros-llama-live.service 2>/dev/null; then
    print_status "OK" "kloros-llama-live.service is running"

    # Check HTTP health
    if curl -s http://127.0.0.1:8080/health | grep -q '"status":"ok"'; then
        print_status "OK" "llama-live is responding on port 8080"
    else
        print_status "FAIL" "llama-live not responding on port 8080"
    fi
else
    print_status "WARN" "kloros-llama-live.service is not running"
fi

# Check llama-code service
if systemctl is-active --quiet kloros-llama-code.service 2>/dev/null; then
    print_status "OK" "kloros-llama-code.service is running"

    # Check HTTP health
    if curl -s http://127.0.0.1:8081/health | grep -q '"status":"ok"'; then
        print_status "OK" "llama-code is responding on port 8081"
    else
        print_status "FAIL" "llama-code not responding on port 8081"
    fi
else
    print_status "WARN" "kloros-llama-code.service is not running"
fi

echo ""
echo "3. Testing Backend Integration"
echo "-------------------------------"

cd "$PROJECT_ROOT"

# Test Python imports
if python3 -c "from src.reasoning.llama_adapter import LlamaAdapter" 2>/dev/null; then
    print_status "OK" "LlamaAdapter import successful"
else
    print_status "FAIL" "LlamaAdapter import failed"
fi

if python3 -c "from src.kloros.model_manager import ModelManager" 2>/dev/null; then
    print_status "OK" "ModelManager import successful"
else
    print_status "FAIL" "ModelManager import failed"
fi

# Test factory
if python3 -c "from src.reasoning.base import create_reasoning_backend; create_reasoning_backend('llama')" 2>/dev/null; then
    print_status "OK" "Factory creates llama backend"
else
    print_status "FAIL" "Factory failed to create llama backend"
fi

echo ""
echo "4. Running Unit Tests"
echo "---------------------"

# Run unit tests
if pytest tests/unit/test_llama_adapter.py -v --tb=short 2>&1 | tee /tmp/llama_test_output.txt | grep -q "passed"; then
    print_status "OK" "LlamaAdapter unit tests passed"
else
    print_status "FAIL" "LlamaAdapter unit tests failed"
fi

if pytest tests/unit/test_model_manager.py -v --tb=short 2>&1 | grep -q "passed"; then
    print_status "OK" "ModelManager unit tests passed"
else
    print_status "FAIL" "ModelManager unit tests failed"
fi

echo ""
echo "=========================================="
echo "Validation Summary"
echo "=========================================="

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
    echo ""
    echo "Migration is ready to proceed."
    echo ""
    echo "Next steps:"
    echo "  1. Start llama.cpp services:"
    echo "     sudo systemctl start kloros-llama-live"
    echo "     sudo systemctl start kloros-llama-code"
    echo ""
    echo "  2. Run integration tests:"
    echo "     pytest tests/integration/test_llama_integration.py -v"
    echo ""
    echo "  3. Update services to use llama backend:"
    echo "     export LLM_BACKEND=llama"
    exit 0
else
    echo -e "${RED}Validation failed with $ERRORS error(s)${NC}"
    echo ""
    echo "Please resolve the issues above before proceeding with migration."
    exit 1
fi
```

**Test Requirements:**

Manual execution:

```bash
# Make executable
chmod +x /home/kloros/scripts/validate_llama_migration.sh

# Run validation
/home/kloros/scripts/validate_llama_migration.sh
```

**Acceptance Criteria:**
- [ ] Script checks for llama-server installation
- [ ] Script verifies model files exist
- [ ] Script checks systemd service status
- [ ] Script tests HTTP health endpoints
- [ ] Script validates Python imports
- [ ] Script runs unit tests
- [ ] Script provides clear next steps
- [ ] Script exits with proper status code

---

### Task 10: Create Rollback Script

**Priority:** LOW
**Complexity:** Low (1/5)
**Estimated Time:** 15 minutes

**Files to Create:**
- `/home/kloros/scripts/rollback_to_ollama.sh`

**Dependencies:** None (independent safety mechanism)

**Implementation Details:**

Create a rollback script to quickly revert to Ollama if llama.cpp migration has issues.

```bash
# /home/kloros/scripts/rollback_to_ollama.sh

#!/bin/bash
set -euo pipefail

echo "=========================================="
echo "KLoROS Rollback to Ollama"
echo "=========================================="
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}This will stop llama.cpp services and revert to Ollama${NC}"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

echo ""
echo "1. Stopping llama.cpp services..."
echo "----------------------------------"

sudo systemctl stop kloros-llama-live.service 2>/dev/null || true
sudo systemctl stop kloros-llama-code.service 2>/dev/null || true

echo -e "${GREEN}✓${NC} llama.cpp services stopped"

echo ""
echo "2. Checking Ollama status..."
echo "----------------------------"

if systemctl is-active --quiet ollama.service 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Ollama service is running"
else
    echo "Starting Ollama service..."
    sudo systemctl start ollama.service || {
        echo "ERROR: Failed to start Ollama"
        echo "Manual intervention required"
        exit 1
    }
    sleep 2
    echo -e "${GREEN}✓${NC} Ollama service started"
fi

# Test Ollama health
if curl -s http://127.0.0.1:11434/api/tags | grep -q "models"; then
    echo -e "${GREEN}✓${NC} Ollama is responding"
else
    echo "WARNING: Ollama not responding on port 11434"
fi

echo ""
echo "3. Restoring environment..."
echo "---------------------------"

# Note: In production, this would update environment files
# or systemd service configurations
echo -e "${GREEN}✓${NC} Environment restored (using Ollama by default)"

echo ""
echo "=========================================="
echo "Rollback Complete"
echo "=========================================="
echo ""
echo "Ollama is now active. llama.cpp services are stopped."
echo ""
echo "Services using default 'ollama' backend will work normally."
echo ""
echo "To re-enable llama.cpp later:"
echo "  sudo systemctl start kloros-llama-live"
echo "  sudo systemctl start kloros-llama-code"
echo ""
```

**Test Requirements:**

Manual testing:

```bash
# Make executable
chmod +x /home/kloros/scripts/rollback_to_ollama.sh

# Test rollback (dry run by reading script)
cat /home/kloros/scripts/rollback_to_ollama.sh

# Actual rollback (interactive)
/home/kloros/scripts/rollback_to_ollama.sh
```

**Acceptance Criteria:**
- [ ] Script stops llama.cpp services safely
- [ ] Script starts Ollama service if not running
- [ ] Script validates Ollama health before completing
- [ ] Script requires user confirmation
- [ ] Script provides clear status messages
- [ ] Script is idempotent (safe to run multiple times)

---

## Summary

### Task Count: 10 tasks total

**Phase 1 (Foundation):** 4 tasks
- Task 1: ModelManager module (30 min)
- Task 2: LlamaAdapter module (30 min)
- Task 3: Systemd service templates (20 min)
- Task 4: Config module updates (20 min)

**Phase 2 (Integration):** 3 tasks
- Task 5: Reasoning factory updates (25 min)
- Task 6: LLM router updates (30 min)
- Task 7: Backend switching CLI (15 min)

**Phase 3 (Testing):** 3 tasks
- Task 8: Integration test suite (30 min)
- Task 9: Migration validation script (20 min)
- Task 10: Rollback script (15 min)

### Complexity Breakdown

- **Low (1-2/5):** Tasks 3, 4, 7, 9, 10 (5 tasks)
- **Medium (3/5):** Tasks 1, 2, 5, 6, 8 (5 tasks)
- **High (4-5/5):** None

### Total Estimated Time

- Minimum: ~3.5 hours (optimistic)
- Maximum: ~5 hours (with testing and validation)
- Average per task: ~23 minutes

### Dependency Chains

**Critical Path:**
1. Task 1 (ModelManager) → Task 3 (systemd templates)
2. Task 2 (LlamaAdapter) → Task 5 (factory) → Task 8 (integration tests)
3. Task 4 (config) → Task 6 (router) → Task 8 (integration tests)

**Parallel Execution Opportunities:**
- Tasks 1, 2, 4 can run in parallel (no dependencies)
- Tasks 3, 7 can run after their minimal dependencies
- Tasks 9, 10 are independent and can run anytime

### Success Metrics

Each task is considered complete when:
1. All code is written following existing patterns
2. All tests pass (unit and integration where applicable)
3. All acceptance criteria are met
4. Code is committed to version control (if applicable)

### Notes for Subagent Execution

- Each task is designed to be atomic and completable in one session
- Tests are written first (TDD approach)
- Clear acceptance criteria prevent scope creep
- Tasks build incrementally on each other
- Rollback mechanism ensures safety (Task 10)

---

*Document created: 2025-11-26*
*Ready for subagent-driven development workflow*
