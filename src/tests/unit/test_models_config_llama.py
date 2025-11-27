import pytest
from src.core.config.models_config import (
    get_llama_url_for_mode,
    get_llama_model_path_for_mode,
    get_llama_context_size,
    check_llama_health
)


def test_get_llama_url_for_mode():
    """Test URL mapping for different modes."""
    assert get_llama_url_for_mode("live") == "http://127.0.0.1:8080"
    assert get_llama_url_for_mode("think") == "http://127.0.0.1:8082"
    assert get_llama_url_for_mode("deep") == "http://127.0.0.1:8082"
    assert get_llama_url_for_mode("code") == "http://127.0.0.1:8081"


def test_get_llama_url_for_mode_default():
    """Test default URL when mode not specified."""
    assert "8080" in get_llama_url_for_mode()


def test_get_llama_model_path_for_mode():
    """Test model path mapping for different modes."""
    live_path = get_llama_model_path_for_mode("live")
    assert "qwen2.5-7b-instruct" in live_path
    assert live_path.endswith(".gguf")

    think_path = get_llama_model_path_for_mode("think")
    assert "deepseek-r1" in think_path
    assert think_path.endswith(".gguf")

    code_path = get_llama_model_path_for_mode("code")
    assert "coder-7b" in code_path
    assert code_path.endswith(".gguf")


def test_get_llama_context_size():
    """Test context size retrieval."""
    assert get_llama_context_size("live") == 32768
    assert get_llama_context_size("code") == 32768


def test_check_llama_health_unreachable():
    """Test health check with unreachable server."""
    result = check_llama_health("http://127.0.0.1:9999")
    assert result is False
