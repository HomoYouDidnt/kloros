"""Unit tests for LLM zooid - test in isolation with mocked UMN and HTTP."""
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.umn_mock import MockUMNPub, MockUMNSub
from src.kloros_voice_llm import LLMZooid


@pytest.fixture
def zooid(monkeypatch):
    """Create LLMZooid with mocked dependencies."""
    monkeypatch.setenv("KLR_ENABLE_LLM", "1")
    monkeypatch.setenv("KLR_OLLAMA_MODEL", "test_model")
    monkeypatch.setenv("KLR_OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("KLR_REMOTE_LLM_MODEL", "test_remote_model")
    monkeypatch.setenv("KLR_DASHBOARD_URL", "http://localhost:5002")

    with patch('src.kloros_voice_llm.UMNPub', MockUMNPub), \
         patch('src.kloros_voice_llm.UMNSub', MockUMNSub):

        zooid = LLMZooid()
        yield zooid

        zooid.shutdown()


class TestLLMZooidInit:
    """Test LLMZooid initialization."""

    def test_init_sets_zooid_name(self, zooid):
        """Test that zooid name is set correctly."""
        assert zooid.zooid_name == "kloros-voice-llm"
        assert zooid.niche == "voice.llm"

    def test_init_statistics(self, zooid):
        """Test that statistics are initialized."""
        assert zooid.stats["total_requests"] == 0
        assert zooid.stats["successful_requests"] == 0
        assert zooid.stats["failed_requests"] == 0
        assert zooid.stats["remote_requests"] == 0
        assert zooid.stats["local_requests"] == 0
        assert zooid.stats["average_latency"] == 0.0
        assert zooid.stats["latencies"] == []

    def test_init_environment_variables(self, zooid):
        """Test that environment variables are read."""
        assert zooid.enable_llm == 1
        assert zooid.ollama_model == "test_model"
        assert zooid.ollama_url == "http://localhost:11434"
        assert zooid.remote_llm_model == "test_remote_model"
        assert zooid.dashboard_url == "http://localhost:5002"

    def test_init_defaults(self, zooid):
        """Test that defaults are set."""
        assert zooid.remote_llm_enabled is False
        assert zooid.remote_timeout == 120
        assert zooid.local_timeout == 60
        assert zooid.max_retries == 1


class TestLLMZooidStart:
    """Test LLMZooid startup."""

    def test_start_emits_ready_signal(self, zooid):
        """Test that start() emits VOICE.LLM.READY signal."""
        with patch.object(zooid, '_check_remote_llm_config'):
            zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.LLM.READY") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.LLM.READY")
        assert msg is not None
        assert msg.ecosystem == "voice"
        assert msg.facts["zooid"] == "kloros-voice-llm"
        assert msg.facts["remote_enabled"] is False
        assert "ollama" in msg.facts["available_backends"]

    def test_start_subscribes_to_llm_request(self, zooid):
        """Test that start() subscribes to VOICE.ORCHESTRATOR.LLM.REQUEST."""
        with patch.object(zooid, '_check_remote_llm_config'):
            zooid.start()

        assert hasattr(zooid, 'llm_request_sub')
        assert zooid.llm_request_sub.topic == "VOICE.ORCHESTRATOR.LLM.REQUEST"

    def test_start_disabled_llm(self, monkeypatch):
        """Test that LLM can be disabled via environment."""
        monkeypatch.setenv("KLR_ENABLE_LLM", "0")

        with patch('src.kloros_voice_llm.UMNPub', MockUMNPub), \
             patch('src.kloros_voice_llm.UMNSub', MockUMNSub):
            zooid = LLMZooid()
            zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.LLM.READY") == 0


class TestRemoteLLMConfiguration:
    """Test remote LLM configuration."""

    def test_check_remote_llm_config_success(self, zooid):
        """Test successful remote LLM configuration check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "enabled": True,
            "selected_model": "remote_test_model"
        }

        with patch('requests.get', return_value=mock_response):
            zooid._check_remote_llm_config()

        assert zooid.remote_llm_enabled is True
        assert zooid.remote_llm_model == "remote_test_model"

    def test_check_remote_llm_config_disabled(self, zooid):
        """Test remote LLM configuration disabled."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "enabled": False,
            "selected_model": "test_model"
        }

        with patch('requests.get', return_value=mock_response):
            zooid._check_remote_llm_config()

        assert zooid.remote_llm_enabled is False

    def test_check_remote_llm_config_failure(self, zooid):
        """Test remote LLM configuration check failure."""
        with patch('requests.get', side_effect=Exception("Connection failed")):
            zooid._check_remote_llm_config()

        assert zooid.remote_llm_enabled is False

    def test_check_remote_llm_config_http_error(self, zooid):
        """Test remote LLM configuration HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 404

        with patch('requests.get', return_value=mock_response):
            zooid._check_remote_llm_config()

        assert zooid.remote_llm_enabled is False


class TestRemoteLLMQuery:
    """Test remote LLM query functionality."""

    def test_query_remote_llm_success(self, zooid):
        """Test successful remote LLM query."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "response": "Remote LLM test response"
        }

        with patch('requests.post', return_value=mock_response):
            success, response = zooid._query_remote_llm("test prompt")

        assert success is True
        assert response == "Remote LLM test response"

    def test_query_remote_llm_error(self, zooid):
        """Test remote LLM query error."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": False,
            "error": "Model not found"
        }

        with patch('requests.post', return_value=mock_response):
            success, response = zooid._query_remote_llm("test prompt")

        assert success is False
        assert "Model not found" in response

    def test_query_remote_llm_http_error(self, zooid):
        """Test remote LLM query HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch('requests.post', return_value=mock_response):
            success, response = zooid._query_remote_llm("test prompt")

        assert success is False
        assert "HTTP 500" in response

    def test_query_remote_llm_timeout(self, zooid):
        """Test remote LLM query timeout."""
        import requests

        with patch('requests.post', side_effect=requests.Timeout):
            success, response = zooid._query_remote_llm("test prompt")

        assert success is False
        assert "timeout" in response

    def test_query_remote_llm_exception(self, zooid):
        """Test remote LLM query exception."""
        with patch('requests.post', side_effect=Exception("Connection error")):
            success, response = zooid._query_remote_llm("test prompt")

        assert success is False
        assert "failed" in response


class TestOllamaQuery:
    """Test Ollama query functionality."""

    def test_query_ollama_success(self, zooid):
        """Test successful Ollama query."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Ollama test response"
        }

        with patch('requests.post', return_value=mock_response):
            response = zooid._query_ollama("test prompt")

        assert response == "Ollama test response"

    def test_query_ollama_http_error(self, zooid):
        """Test Ollama query HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch('requests.post', return_value=mock_response):
            response = zooid._query_ollama("test prompt")

        assert "Error: Ollama HTTP 500" in response

    def test_query_ollama_timeout(self, zooid):
        """Test Ollama query timeout."""
        import requests

        with patch('requests.post', side_effect=requests.Timeout):
            response = zooid._query_ollama("test prompt")

        assert "timeout" in response

    def test_query_ollama_exception(self, zooid):
        """Test Ollama query exception."""
        import requests

        with patch('requests.post', side_effect=requests.RequestException("Connection error")):
            response = zooid._query_ollama("test prompt")

        assert "Ollama error" in response

    def test_query_ollama_streaming_success(self, zooid):
        """Test successful Ollama streaming query."""
        mock_lines = [
            b'{"response": "Test ", "done": false}',
            b'{"response": "response", "done": true}'
        ]
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = mock_lines

        with patch('requests.post', return_value=mock_response):
            response = zooid._query_ollama_streaming("test prompt")

        assert response == "Test response"

    def test_query_ollama_streaming_http_error(self, zooid):
        """Test Ollama streaming query HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch('requests.post', return_value=mock_response):
            response = zooid._query_ollama_streaming("test prompt")

        assert "Error: Ollama HTTP 500" in response


class TestLLMRequestHandling:
    """Test LLM request handling and retry logic."""

    def test_on_llm_request_success_remote(self, zooid):
        """Test successful LLM request with remote backend."""
        zooid.start()

        zooid.remote_llm_enabled = True

        mock_check = Mock()
        mock_query = Mock(return_value=(True, "Remote response"))
        with patch.object(zooid, '_check_remote_llm_config', mock_check), \
             patch.object(zooid, '_query_remote_llm', mock_query):
            zooid._on_llm_request({
                "facts": {
                    "prompt": "test prompt",
                    "mode": "non-streaming"
                }
            })

        assert zooid.stats["successful_requests"] == 1
        assert zooid.stats["remote_requests"] == 1
        assert zooid.chem_pub.get_signal_count("VOICE.LLM.RESPONSE") == 1

    def test_on_llm_request_success_local(self, zooid):
        """Test successful LLM request with local backend."""
        zooid.remote_llm_enabled = False
        zooid.start()

        mock_query = Mock(return_value="Local response")
        with patch.object(zooid, '_query_ollama', mock_query):
            zooid._on_llm_request({
                "facts": {
                    "prompt": "test prompt",
                    "mode": "non-streaming"
                }
            })

        assert zooid.stats["successful_requests"] == 1
        assert zooid.stats["local_requests"] == 1
        assert zooid.chem_pub.get_signal_count("VOICE.LLM.RESPONSE") == 1

    def test_on_llm_request_retry_fallback(self, zooid):
        """Test retry logic with remote failure -> local success."""
        zooid.start()

        zooid.remote_llm_enabled = True

        mock_check = Mock()
        mock_remote_query = Mock(return_value=(False, "Remote failed"))
        mock_local_query = Mock(return_value="Local response")

        with patch.object(zooid, '_check_remote_llm_config', mock_check), \
             patch.object(zooid, '_query_remote_llm', mock_remote_query), \
             patch.object(zooid, '_query_ollama', mock_local_query):
            zooid._on_llm_request({
                "facts": {
                    "prompt": "test prompt",
                    "mode": "non-streaming"
                }
            })

        assert zooid.stats["successful_requests"] == 1
        assert zooid.stats["local_requests"] == 1

    def test_on_llm_request_all_fail(self, zooid):
        """Test all backends failing."""
        zooid.max_retries = 1
        zooid.start()

        zooid.remote_llm_enabled = True

        mock_check = Mock()
        mock_remote_query = Mock(return_value=(False, "Remote failed"))
        mock_local_query = Mock(return_value="Error: Ollama failed")

        with patch.object(zooid, '_check_remote_llm_config', mock_check), \
             patch.object(zooid, '_query_remote_llm', mock_remote_query), \
             patch.object(zooid, '_query_ollama', mock_local_query):
            zooid._on_llm_request({
                "facts": {
                    "prompt": "test prompt",
                    "mode": "non-streaming"
                }
            })

        assert zooid.stats["failed_requests"] == 1
        assert zooid.chem_pub.get_signal_count("VOICE.LLM.ERROR") == 1

    def test_on_llm_request_missing_prompt(self, zooid):
        """Test handling of missing prompt."""
        zooid.start()

        zooid._on_llm_request({
            "facts": {}
        })

        assert zooid.chem_pub.get_signal_count("VOICE.LLM.ERROR") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.LLM.ERROR")
        assert msg.facts["error_type"] == "missing_prompt"

    def test_on_llm_request_streaming_mode(self, zooid):
        """Test LLM request with streaming mode."""
        zooid.start()

        mock_query = Mock(return_value="Streamed response")
        with patch.object(zooid, '_query_ollama_streaming', mock_query):
            zooid._on_llm_request({
                "facts": {
                    "prompt": "test prompt",
                    "mode": "streaming"
                }
            })

        assert mock_query.called
        assert zooid.stats["successful_requests"] == 1


class TestLLMSignalEmission:
    """Test UMN signal emission."""

    def test_emit_response(self, zooid):
        """Test emission of VOICE.LLM.RESPONSE signal."""
        zooid.start()

        zooid._emit_response(
            prompt="test prompt",
            response="test response",
            model="test_model",
            backend="ollama",
            latency=1.23,
            temperature=0.8,
            incident_id="test-001"
        )

        assert zooid.chem_pub.get_signal_count("VOICE.LLM.RESPONSE") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.LLM.RESPONSE")
        assert msg.facts["response"] == "test response"
        assert msg.facts["model"] == "test_model"
        assert msg.facts["backend"] == "ollama"
        assert msg.facts["latency"] == 1.23
        assert msg.incident_id == "test-001"

    def test_emit_error(self, zooid):
        """Test emission of VOICE.LLM.ERROR signal."""
        zooid.start()

        zooid._emit_error(
            error_type="generation_failed",
            details="All backends failed",
            attempt_count=2,
            incident_id="test-002"
        )

        assert zooid.chem_pub.get_signal_count("VOICE.LLM.ERROR") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.LLM.ERROR")
        assert msg.facts["error_type"] == "generation_failed"
        assert msg.facts["details"] == "All backends failed"
        assert msg.facts["attempt_count"] == 2
        assert msg.incident_id == "test-002"


class TestLLMStatistics:
    """Test LLM statistics tracking."""

    def test_get_stats(self, zooid):
        """Test getting LLM statistics."""
        stats = zooid.get_stats()

        assert "total_requests" in stats
        assert "successful_requests" in stats
        assert "failed_requests" in stats
        assert "remote_requests" in stats
        assert "local_requests" in stats
        assert "average_latency" in stats
        assert "remote_enabled" in stats

    def test_statistics_count_requests(self, zooid):
        """Test that statistics count requests correctly."""
        zooid.remote_llm_enabled = False
        zooid.start()

        mock_query = Mock(return_value="Response")
        with patch.object(zooid, '_query_ollama', mock_query):
            zooid._on_llm_request({"facts": {"prompt": "prompt1"}})
            zooid._on_llm_request({"facts": {"prompt": "prompt2"}})
            zooid._on_llm_request({"facts": {"prompt": "prompt3"}})

        stats = zooid.get_stats()
        assert stats["total_requests"] == 3
        assert stats["successful_requests"] == 3
        assert stats["failed_requests"] == 0

    def test_statistics_track_latencies(self, zooid):
        """Test that latencies are tracked."""
        zooid.remote_llm_enabled = False
        zooid.start()

        mock_query = Mock(return_value="Response")
        with patch.object(zooid, '_query_ollama', mock_query):
            zooid._on_llm_request({"facts": {"prompt": "prompt"}})

        assert len(zooid.stats["latencies"]) == 1
        assert zooid.stats["latencies"][0] > 0

    def test_statistics_limit_latencies_history(self, zooid):
        """Test that latencies history is limited to 100."""
        zooid.remote_llm_enabled = False
        zooid.start()

        mock_query = Mock(return_value="Response")
        with patch.object(zooid, '_query_ollama', mock_query):
            for i in range(150):
                zooid._on_llm_request({"facts": {"prompt": f"prompt{i}"}})

        assert len(zooid.stats["latencies"]) == 100


class TestLLMZooidShutdown:
    """Test LLMZooid shutdown."""

    def test_shutdown_emits_signal(self, zooid):
        """Test that shutdown emits VOICE.LLM.SHUTDOWN signal."""
        zooid.start()
        zooid.shutdown()

        assert zooid.chem_pub.get_signal_count("VOICE.LLM.SHUTDOWN") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.LLM.SHUTDOWN")
        assert "stats" in msg.facts

    def test_shutdown_stops_processing(self, zooid):
        """Test that shutdown stops processing."""
        zooid.start()
        zooid.shutdown()

        assert not zooid.running

        zooid._on_llm_request({
            "facts": {
                "prompt": "test prompt"
            }
        })

        assert zooid.chem_pub.get_signal_count("VOICE.LLM.RESPONSE") == 0
