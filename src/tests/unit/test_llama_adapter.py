import pytest
from unittest.mock import Mock, patch, MagicMock
from src.cognition.reasoning.llama_adapter import LlamaAdapter
from src.cognition.reasoning.base import ReasoningResult


@pytest.fixture
def adapter():
    return LlamaAdapter(
        base_url="http://127.0.0.1:8080",
        model="test-model",
        system_prompt="You are a helpful assistant.",
        temperature=0.7
    )


def test_adapter_init(adapter):
    assert adapter.base_url == "http://127.0.0.1:8080"
    assert adapter.model == "test-model"
    assert adapter.system_prompt == "You are a helpful assistant."
    assert adapter.temperature == 0.7


def test_build_prompt_with_system(adapter):
    prompt = adapter._build_prompt("Hello", system="You are a test bot.")
    assert "You are a test bot." in prompt
    assert "Hello" in prompt


def test_build_prompt_without_system():
    adapter = LlamaAdapter(base_url="http://127.0.0.1:8080", system_prompt="")
    prompt = adapter._build_prompt("Hello")
    assert prompt == "Hello"


@patch('requests.post')
def test_generate_success(mock_post, adapter):
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
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": "Response"}
    mock_post.return_value = mock_response

    adapter.generate("Hello", temperature=0.9, top_p=0.8, repeat_penalty=1.2)

    payload = mock_post.call_args[1]["json"]
    assert payload["temperature"] == 0.9
    assert payload["top_p"] == 0.8
    assert payload["repeat_penalty"] == 1.2


@patch('requests.post')
def test_reply_non_streaming(mock_post, adapter):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": "Test reply"}
    mock_post.return_value = mock_response

    result = adapter.reply("Hello", enable_streaming=False)

    assert isinstance(result, ReasoningResult)
    assert result.reply_text == "Test reply"


@patch('requests.get')
def test_health_check_ok(mock_get, adapter):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}
    mock_get.return_value = mock_response

    assert adapter.health_check() is True


@patch('requests.get')
def test_health_check_fail(mock_get, adapter):
    mock_get.side_effect = Exception("Connection refused")
    assert adapter.health_check() is False
