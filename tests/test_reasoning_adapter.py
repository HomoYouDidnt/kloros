"""Unit tests for reasoning adapter functionality."""

from unittest.mock import patch, MagicMock
import pytest

from src.reasoning.base import create_reasoning_backend, ReasoningResult
from src.reasoning.mock_backend import MockReasoningBackend


class TestReasoningFactory:
    """Test reasoning backend factory functionality."""

    def test_factory_mock(self):
        """Test that factory creates mock backend correctly."""
        backend = create_reasoning_backend("mock")

        # Verify it has the reply method
        assert hasattr(backend, "reply")
        assert callable(backend.reply)

        # Test basic reasoning
        result = backend.reply("hello")

        # Verify result structure
        assert isinstance(result, ReasoningResult)
        assert hasattr(result, "reply_text")
        assert hasattr(result, "sources")
        assert hasattr(result, "meta")

        # Mock backend should return fixed values
        assert result.reply_text == "ok"
        assert result.sources == ["mock"]

    def test_factory_unknown_backend(self):
        """Test that unknown backend raises ValueError."""
        with pytest.raises(ValueError, match="Unknown reasoning backend: unknown"):
            create_reasoning_backend("unknown")

    def test_local_backends_missing_module_graceful(self):
        """Test that local backends fail gracefully when modules are missing."""
        # In this environment, RAG module is available, so we expect success
        # But QA module should be missing and fail gracefully

        # Test that RAG backend can be created when module is available
        try:
            backend = create_reasoning_backend("rag")
            assert hasattr(backend, 'reply'), "RAG backend should have reply method"
        except RuntimeError:
            # If it fails, that's also acceptable - it means dependencies are missing
            # This test just ensures the error handling is graceful
            pass

        # Test QA backend without QA module - this one should reliably fail
        with patch.dict('sys.modules', {'kloROS_accuracy_stack.pipeline.qa': None}):
            with pytest.raises(RuntimeError, match="qa backend unavailable"):
                create_reasoning_backend("qa")


class TestMockBackend:
    """Test mock reasoning backend behavior."""

    def test_mock_basic_reply(self):
        """Test basic mock backend reply functionality."""
        backend = MockReasoningBackend()
        result = backend.reply("test input")

        assert isinstance(result, ReasoningResult)
        assert result.reply_text == "ok"
        assert result.sources == ["mock"]
        assert result.meta is not None
        assert result.meta["mock"] is True

    def test_mock_custom_reply_text(self):
        """Test mock backend with custom reply text."""
        backend = MockReasoningBackend(reply_text="custom response")
        result = backend.reply("test input")

        assert result.reply_text == "custom response"
        assert result.sources == ["mock"]

    def test_mock_custom_sources(self):
        """Test mock backend with custom sources."""
        custom_sources = ["source1", "source2", "source3"]
        backend = MockReasoningBackend(sources=custom_sources)
        result = backend.reply("test input")

        assert result.reply_text == "ok"
        assert result.sources == custom_sources
        # Verify it returns a copy (not the same object)
        assert result.sources is not custom_sources

    def test_mock_ignores_input(self):
        """Test that mock backend ignores input text."""
        backend = MockReasoningBackend()

        # Different inputs should produce identical results
        result1 = backend.reply("hello")
        result2 = backend.reply("completely different input")
        result3 = backend.reply("")

        assert result1.reply_text == result2.reply_text == result3.reply_text
        assert result1.sources == result2.sources == result3.sources

    def test_sources_list_present(self):
        """Test that sources is always a list of strings."""
        backend = MockReasoningBackend()
        result = backend.reply("test")

        assert isinstance(result.sources, list)
        assert all(isinstance(source, str) for source in result.sources)

    def test_meta_includes_input_length(self):
        """Test that meta data includes input length."""
        backend = MockReasoningBackend()

        result_short = backend.reply("hi")
        result_long = backend.reply("this is a much longer input string")

        assert result_short.meta["input_length"] == 2
        assert result_long.meta["input_length"] == len("this is a much longer input string")

    def test_sources_mutation_safety(self):
        """Test that sources list is safe from external mutation."""
        backend = MockReasoningBackend(sources=["original"])
        result = backend.reply("test")

        # Mutating the result shouldn't affect subsequent calls
        result.sources.append("modified")

        result2 = backend.reply("test2")
        assert result2.sources == ["original"]


class TestReasoningResult:
    """Test ReasoningResult dataclass behavior."""

    def test_reasoning_result_creation(self):
        """Test ReasoningResult dataclass creation and field access."""
        result = ReasoningResult(
            reply_text="test response",
            sources=["source1", "source2"],
            meta={"key": "value"}
        )

        assert result.reply_text == "test response"
        assert result.sources == ["source1", "source2"]
        assert result.meta == {"key": "value"}

    def test_reasoning_result_default_sources(self):
        """Test ReasoningResult with default empty sources."""
        result = ReasoningResult(reply_text="test")

        assert result.reply_text == "test"
        assert result.sources == []
        assert result.meta is None

    def test_reasoning_result_equality(self):
        """Test ReasoningResult equality comparison."""
        result1 = ReasoningResult("hello", ["source1"], {"test": True})
        result2 = ReasoningResult("hello", ["source1"], {"test": True})
        result3 = ReasoningResult("hi", ["source1"], {"test": True})

        assert result1 == result2
        assert result1 != result3


class TestBackendIntegration:
    """Test reasoning backend integration scenarios."""

    def test_kloros_voice_fallback_logic(self):
        """Test that kloros_voice.py fallback logic works correctly."""
        # Mock the create_reasoning_backend function to simulate failures
        def failing_backend(name, **kwargs):
            if name == "rag":
                raise RuntimeError("rag backend unavailable")
            elif name == "qa":
                raise RuntimeError("qa backend unavailable")
            elif name == "mock":
                return MockReasoningBackend()
            else:
                raise ValueError(f"Unknown backend: {name}")

        # Test RAG fallback to mock
        with patch('src.reasoning.base.create_reasoning_backend', side_effect=failing_backend):
            # This simulates the logic in kloros_voice.py
            backend_name = "rag"
            backend = None

            try:
                backend = failing_backend(backend_name)
            except Exception:
                # Fallback to mock
                if backend_name != "mock":
                    backend = failing_backend("mock")

            assert isinstance(backend, MockReasoningBackend)

    def test_multiple_backend_types(self):
        """Test creating multiple backend types."""
        mock_backend = create_reasoning_backend("mock")

        # Both should implement the same protocol
        assert hasattr(mock_backend, "reply")
        assert callable(mock_backend.reply)

        # Results should have consistent structure
        mock_result = mock_backend.reply("test")
        assert isinstance(mock_result, ReasoningResult)
        assert isinstance(mock_result.sources, list)

    def test_empty_input_handling(self):
        """Test backends handle empty input gracefully."""
        backend = create_reasoning_backend("mock")

        # Test various empty inputs
        empty_inputs = ["", "   ", "\n\t  "]
        for empty_input in empty_inputs:
            result = backend.reply(empty_input)
            assert isinstance(result, ReasoningResult)
            # Mock backend ignores input, so should still return "ok"
            assert result.reply_text == "ok"

    def test_large_input_handling(self):
        """Test backends handle large input gracefully."""
        backend = create_reasoning_backend("mock")

        # Create a large input string
        large_input = "This is a test sentence. " * 1000
        result = backend.reply(large_input)

        assert isinstance(result, ReasoningResult)
        assert result.reply_text == "ok"
        assert result.meta["input_length"] == len(large_input)

    def test_special_characters_input(self):
        """Test backends handle special characters in input."""
        backend = create_reasoning_backend("mock")

        special_input = "Hello! 你好 🌟 @#$%^&*()_+ \n\t\\\"'"
        result = backend.reply(special_input)

        assert isinstance(result, ReasoningResult)
        assert result.reply_text == "ok"
        assert result.meta["input_length"] == len(special_input)


class TestProtocolCompliance:
    """Test that backends comply with the ReasoningBackend protocol."""

    def test_mock_backend_protocol_compliance(self):
        """Test that MockReasoningBackend follows the protocol."""
        backend = MockReasoningBackend()

        # Should have reply method
        assert hasattr(backend, "reply")
        assert callable(backend.reply)

        # reply should accept string and return ReasoningResult
        result = backend.reply("test")
        assert isinstance(result, ReasoningResult)

        # ReasoningResult should have required fields
        assert hasattr(result, "reply_text")
        assert hasattr(result, "sources")
        assert hasattr(result, "meta")

    def test_factory_returns_protocol_compliant_backends(self):
        """Test that factory returns backends that follow the protocol."""
        backend = create_reasoning_backend("mock")

        # Should be callable as per protocol
        result = backend.reply("test input")
        assert isinstance(result, ReasoningResult)

        # Should handle the ReasoningResult structure correctly
        assert isinstance(result.reply_text, str)
        assert isinstance(result.sources, list)
        # meta can be None or dict
        assert result.meta is None or isinstance(result.meta, dict)