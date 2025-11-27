import pytest
import requests
from pathlib import Path
from src.cognition.reasoning.base import create_reasoning_backend, ReasoningResult
from src.cognition.reasoning.llama_adapter import LlamaAdapter
from src.cognition.reasoning.llm_router import LLMRouter, LLMMode
from src.core.model_manager import ModelManager


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
    assert any(m["name"] == "qwen2.5:7b" for m in models)


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

    is_healthy, error = router.check_service_health(LLMMode.LIVE)
    assert is_healthy is True
    assert error == ""

    service = router.get_service(LLMMode.LIVE)
    assert service.port == 8080


def test_llama_backend_compatibility_with_ollama_interface(llama_service_running):
    """Test llama.cpp adapter is compatible with Ollama interface."""
    llama_backend = create_reasoning_backend("llama", mode="live")

    assert hasattr(llama_backend, "generate")
    assert hasattr(llama_backend, "reply")

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

    long_text = "The quick brown fox jumps over the lazy dog. " * 100
    prompt = f"Summarize this text in one sentence:\n\n{long_text}"

    response = adapter.generate(prompt)

    assert response is not None
    assert len(response) > 0
    assert len(response) < len(prompt)


def test_backend_switching():
    """Test that backends can be switched via factory."""
    try:
        ollama_backend = create_reasoning_backend("ollama")
        assert ollama_backend is not None
    except Exception:
        pytest.skip("Ollama not available")

    llama_backend = create_reasoning_backend("llama", mode="live")
    assert llama_backend is not None

    assert type(ollama_backend) != type(llama_backend)
    assert hasattr(ollama_backend, "generate")
    assert hasattr(llama_backend, "generate")
