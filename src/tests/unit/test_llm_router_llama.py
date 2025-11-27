"""
Tests for LLMRouter llama.cpp backend support (Task 6).

Verifies that LLMRouter can be initialized with different backends:
- "ollama": Uses Ollama services on ports 11434/11435
- "llama": Uses llama.cpp services on ports 8080/8081

Tests health check fallback logic:
- Try /health endpoint first (llama.cpp)
- Fall back to /api/tags endpoint (Ollama)
"""

import pytest
from unittest.mock import Mock, patch
from reasoning.llm_router import LLMRouter, LLMMode


@pytest.fixture
def llama_router():
    """Create LLM router with llama.cpp backend."""
    return LLMRouter(backend="llama")


@pytest.fixture
def ollama_router():
    """Create LLM router with Ollama backend."""
    return LLMRouter(backend="ollama")


class TestLlamaBackendInit:
    """Test llama.cpp backend initialization."""

    def test_llama_router_init_with_llama_backend(self, llama_router):
        """Test router initializes with llama backend."""
        assert llama_router.backend == "llama"

    def test_ollama_router_init_with_ollama_backend(self, ollama_router):
        """Test router initializes with ollama backend."""
        assert ollama_router.backend == "ollama"

    def test_default_backend_is_ollama(self):
        """Test that default backend is ollama."""
        router = LLMRouter()
        assert router.backend == "ollama"

    def test_backend_case_insensitive(self):
        """Test that backend parameter is case insensitive."""
        router_upper = LLMRouter(backend="LLAMA")
        router_mixed = LLMRouter(backend="Llama")
        assert router_upper.backend == "llama"
        assert router_mixed.backend == "llama"


class TestLlamaServicePorts:
    """Test llama.cpp services use correct ports."""

    def test_llama_live_mode_uses_port_8080(self, llama_router):
        """LIVE mode should route to llama.cpp on port 8080."""
        service = llama_router.get_service(LLMMode.LIVE)
        assert service.port == 8080
        assert "8080" in service.url

    def test_llama_think_mode_uses_port_8082(self, llama_router):
        """THINK mode should route to llama-think on port 8082."""
        service = llama_router.get_service(LLMMode.THINK)
        assert service.port == 8082
        assert "8082" in service.url

    def test_llama_deep_mode_uses_port_8082(self, llama_router):
        """DEEP mode should route to llama-think on port 8082."""
        service = llama_router.get_service(LLMMode.DEEP)
        assert service.port == 8082
        assert "8082" in service.url

    def test_llama_code_mode_uses_port_8081(self, llama_router):
        """CODE mode should route to llama-code on port 8081."""
        service = llama_router.get_service(LLMMode.CODE)
        assert service.port == 8081
        assert "8081" in service.url

    def test_ollama_live_mode_uses_port_11434(self, ollama_router):
        """LIVE mode should route to ollama-live on port 11434."""
        service = ollama_router.get_service(LLMMode.LIVE)
        assert service.port == 11434
        assert "11434" in service.url

    def test_ollama_code_mode_uses_port_11435(self, ollama_router):
        """CODE mode should route to ollama-think on port 11435."""
        service = ollama_router.get_service(LLMMode.CODE)
        assert service.port == 11435
        assert "11435" in service.url


class TestLlamaServiceModels:
    """Test llama.cpp services use correct models."""

    def test_llama_live_uses_qwen_instruct(self, llama_router):
        """LIVE mode should use qwen2.5-7b-instruct model."""
        service = llama_router.get_service(LLMMode.LIVE)
        assert "qwen2.5-7b-instruct" in service.model

    def test_llama_think_uses_deepseek_r1(self, llama_router):
        """THINK mode should use deepseek-r1 model."""
        service = llama_router.get_service(LLMMode.THINK)
        assert "deepseek-r1" in service.model

    def test_llama_code_uses_qwen_coder(self, llama_router):
        """CODE mode should use qwen2.5-coder-7b-instruct model."""
        service = llama_router.get_service(LLMMode.CODE)
        assert "qwen2.5-coder-7b-instruct" in service.model

    def test_ollama_services_still_use_correct_models(self, ollama_router):
        """Ollama services should use qwen2.5:32b-instruct-q4_K_M."""
        for mode in [LLMMode.LIVE, LLMMode.THINK, LLMMode.DEEP, LLMMode.CODE]:
            service = ollama_router.get_service(mode)
            assert service.model == "qwen2.5:32b-instruct-q4_K_M"


class TestHealthCheckLlama:
    """Test health check with llama.cpp endpoint priority."""

    @patch('requests.get')
    def test_health_check_llama_healthy_with_status_ok(self, mock_get, llama_router):
        """Test health check with healthy llama.cpp server returning status ok."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_response

        is_healthy, error = llama_router.check_service_health(LLMMode.LIVE)

        assert is_healthy is True
        assert error == ""
        mock_get.assert_called_once()
        call_args = mock_get.call_args[0][0]
        assert "/health" in call_args

    @patch('requests.get')
    def test_health_check_falls_back_to_ollama_endpoint(self, mock_get, llama_router):
        """Test health check falls back to Ollama /api/tags endpoint."""
        mock_response_health_fail = Exception("Not found")
        mock_response_tags = Mock()
        mock_response_tags.status_code = 200

        mock_get.side_effect = [mock_response_health_fail, mock_response_tags]

        is_healthy, error = llama_router.check_service_health(LLMMode.LIVE)

        assert is_healthy is True
        assert error == ""

    @patch('requests.get')
    def test_health_check_connection_error_message(self, mock_get, llama_router):
        """Test health check returns appropriate error on connection failure."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        is_healthy, error = llama_router.check_service_health(LLMMode.LIVE)

        assert is_healthy is False
        assert "connection refused" in error.lower()

    @patch('requests.get')
    def test_health_check_timeout_message(self, mock_get, llama_router):
        """Test health check returns appropriate error on timeout."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Timeout")

        is_healthy, error = llama_router.check_service_health(LLMMode.LIVE)

        assert is_healthy is False
        assert "timeout" in error.lower()

    @patch('requests.get')
    def test_health_check_generic_error_message(self, mock_get, llama_router):
        """Test health check returns appropriate error on generic exception."""
        mock_get.side_effect = Exception("Some error")

        is_healthy, error = llama_router.check_service_health(LLMMode.LIVE)

        assert is_healthy is False
        assert "health check failed" in error.lower()


class TestHealthCheckOllama:
    """Test health check still works with Ollama backend."""

    @patch('requests.get')
    def test_health_check_ollama_with_api_tags(self, mock_get, ollama_router):
        """Test health check with Ollama /api/tags endpoint."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        is_healthy, error = ollama_router.check_service_health(LLMMode.LIVE)

        assert is_healthy is True
        assert error == ""


class TestBackendConsistency:
    """Test that backend choice is consistently applied."""

    def test_all_modes_use_same_backend_llama(self, llama_router):
        """Test that all modes use llama backend services."""
        for mode in [LLMMode.LIVE, LLMMode.THINK, LLMMode.DEEP, LLMMode.CODE]:
            service = llama_router.get_service(mode)
            assert service.port in [8080, 8081, 8082], f"Mode {mode} not using llama ports"

    def test_all_modes_use_same_backend_ollama(self, ollama_router):
        """Test that all modes use Ollama backend services."""
        for mode in [LLMMode.LIVE, LLMMode.THINK, LLMMode.DEEP, LLMMode.CODE]:
            service = ollama_router.get_service(mode)
            assert service.port in [11434, 11435], f"Mode {mode} not using Ollama ports"

    def test_service_names_match_backend(self, llama_router, ollama_router):
        """Test that service names match the backend type."""
        for mode in [LLMMode.LIVE, LLMMode.THINK, LLMMode.DEEP]:
            llama_service = llama_router.get_service(mode)
            ollama_service = ollama_router.get_service(mode)
            assert "llama" in llama_service.name.lower()
            assert "ollama" in ollama_service.name.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
