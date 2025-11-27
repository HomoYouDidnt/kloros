import pytest
from src.cognition.reasoning.base import create_reasoning_backend
from src.cognition.reasoning.llama_adapter import LlamaAdapter


def test_create_llama_backend():
    """Test creating llama.cpp backend."""
    backend = create_reasoning_backend("llama", mode="live")
    assert isinstance(backend, LlamaAdapter)


def test_create_llama_backend_with_mode():
    """Test creating llama.cpp backend with specific mode."""
    backend = create_reasoning_backend("llama", mode="code")
    assert isinstance(backend, LlamaAdapter)
    assert "8081" in backend.base_url


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
    assert "8080" in backend.base_url


def test_ollama_backend_still_works():
    """Test that existing Ollama backend still works."""
    from src.cognition.reasoning.base import OllamaReasoner

    backend = create_reasoning_backend("ollama")
    assert isinstance(backend, OllamaReasoner)
