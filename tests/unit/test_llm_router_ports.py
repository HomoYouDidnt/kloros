"""
Tests for LLMRouter port configuration (Phase 4.1).

Verifies that LLMRouter correctly routes to Ollama instances on:
- Port 11434 for ollama-live (LIVE, DEEP modes)
- Port 11435 for ollama-think (THINK, CODE modes)
"""

import pytest
from reasoning.llm_router import LLMRouter, LLMMode, LLMService


class TestLLMRouterPorts:
    """Test LLMRouter endpoint configuration."""

    def setup_method(self):
        """Initialize router for each test."""
        self.router = LLMRouter()

    def test_live_mode_uses_port_11434(self):
        """LIVE mode should route to ollama-live on port 11434."""
        service = self.router.get_service(LLMMode.LIVE)
        assert service.name == "ollama-live"
        assert service.port == 11434
        assert "11434" in service.url

    def test_think_mode_uses_port_11435(self):
        """THINK mode should route to ollama-think on port 11435."""
        service = self.router.get_service(LLMMode.THINK)
        assert service.name == "ollama-think"
        assert service.port == 11435
        assert "11435" in service.url

    def test_deep_mode_uses_port_11434(self):
        """DEEP mode should route to ollama-live on port 11434."""
        service = self.router.get_service(LLMMode.DEEP)
        assert service.name == "ollama-live"
        assert service.port == 11434
        assert "11434" in service.url

    def test_code_mode_uses_port_11435(self):
        """CODE mode should route to ollama-think on port 11435."""
        service = self.router.get_service(LLMMode.CODE)
        assert service.name == "ollama-think"
        assert service.port == 11435
        assert "11435" in service.url

    def test_no_hardcoded_port_8001(self):
        """Port 8001 (old vLLM) should not be used."""
        for mode, service in self.router.SERVICES.items():
            assert service.port != 8001, f"{mode.value} incorrectly uses port 8001"

    def test_no_hardcoded_port_8002(self):
        """Port 8002 (old vLLM) should not be used."""
        for mode, service in self.router.SERVICES.items():
            assert service.port != 8002, f"{mode.value} incorrectly uses port 8002"

    def test_service_url_construction(self):
        """Service URLs should be properly constructed as http://127.0.0.1:{port}."""
        service = self.router.get_service(LLMMode.LIVE)
        assert service.url == "http://127.0.0.1:11434"

    def test_model_is_qwen2_5_instruct(self):
        """All services should use qwen2.5:32b-instruct-q4_K_M model."""
        for mode, service in self.router.SERVICES.items():
            assert service.model == "qwen2.5:32b-instruct-q4_K_M", \
                f"{mode.value} uses wrong model: {service.model}"

    def test_get_available_services_includes_local(self):
        """get_available_services should list all local services."""
        services = self.router.get_available_services()
        assert "local" in services
        local = services["local"]

        assert "live" in local
        assert local["live"]["port"] == 11434
        assert local["live"]["name"] == "ollama-live"

        assert "think" in local
        assert local["think"]["port"] == 11435
        assert local["think"]["name"] == "ollama-think"

    def test_get_available_services_no_port_8001_8002(self):
        """get_available_services should not reference old ports."""
        services = self.router.get_available_services()
        local = services["local"]

        all_services_str = str(local)
        assert "8001" not in all_services_str, "Port 8001 found in services"
        assert "8002" not in all_services_str, "Port 8002 found in services"


class TestLLMServiceDataclass:
    """Test LLMService configuration dataclass."""

    def test_service_creates_url_from_port(self):
        """LLMService should construct URL from port."""
        service = LLMService(
            name="test",
            port=11434,
            model="test-model",
            description="Test service"
        )
        assert service.url == "http://127.0.0.1:11434"

    def test_service_uses_provided_url(self):
        """LLMService should use provided URL if given."""
        custom_url = "http://custom:9999"
        service = LLMService(
            name="test",
            port=11434,
            model="test-model",
            description="Test service",
            url=custom_url
        )
        assert service.url == custom_url


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
