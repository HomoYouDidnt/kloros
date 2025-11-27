"""Integration tests for STT → Intent/Emotion signal flow (Phase 2).

Tests the communication between STT, Intent, and Emotion zooids via real UMN.
No mocks for UMN - uses actual UMN pub/sub with real signal coordination.
"""
import os
import sys
import time
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.orchestration.core.umn_bus_v2 import UMNPub, UMNSub
from src.kloros_voice_intent import IntentZooid
from src.kloros_voice_emotion import EmotionZooid


@pytest.mark.integration
class TestSTTIntentIntegration:
    """Test STT → Intent Classification signal coordination."""

    def test_transcription_to_intent_flow(self, monkeypatch):
        """Test full flow: VOICE.STT.TRANSCRIPTION → VOICE.INTENT.CLASSIFIED."""
        monkeypatch.setenv("KLR_ENABLE_INTENT", "1")

        received_intent = threading.Event()
        intent_data = {}

        def on_intent_classified(msg):
            """Callback for intent classification signal."""
            intent_data.update(msg.get("facts", {}))
            received_intent.set()

        zooid = IntentZooid()
        zooid.start()

        try:
            intent_sub = UMNSub(
                "VOICE.INTENT.CLASSIFIED",
                on_intent_classified,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.STT.TRANSCRIPTION",
                ecosystem="voice",
                intensity=0.95,
                facts={
                    "text": "enroll me",
                    "confidence": 0.95,
                    "language": "en-US"
                },
                incident_id="intent-test-001"
            )

            assert received_intent.wait(timeout=5.0), "Intent classification signal not received"

            assert intent_data["text"] == "enroll me"
            assert intent_data["intent_type"] == "command"
            assert intent_data["command_type"] == "enrollment"
            assert intent_data["confidence"] == 0.95

            intent_sub.close()
            pub.close()

        finally:
            zooid.shutdown()

    def test_question_classification(self, monkeypatch):
        """Test classification of question utterance."""
        monkeypatch.setenv("KLR_ENABLE_INTENT", "1")

        received_intent = threading.Event()
        intent_data = {}

        def on_intent_classified(msg):
            intent_data.update(msg.get("facts", {}))
            received_intent.set()

        zooid = IntentZooid()
        zooid.start()

        try:
            intent_sub = UMNSub(
                "VOICE.INTENT.CLASSIFIED",
                on_intent_classified,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.STT.TRANSCRIPTION",
                ecosystem="voice",
                intensity=0.90,
                facts={
                    "text": "what is the weather today?",
                    "confidence": 0.90,
                    "language": "en-US"
                }
            )

            assert received_intent.wait(timeout=5.0), "Intent classification signal not received"

            assert intent_data["intent_type"] == "question"
            assert intent_data["command_type"] is None
            assert intent_data["confidence"] == 0.85

            intent_sub.close()
            pub.close()

        finally:
            zooid.shutdown()

    def test_conversational_classification(self, monkeypatch):
        """Test classification of conversational utterance."""
        monkeypatch.setenv("KLR_ENABLE_INTENT", "1")

        received_intent = threading.Event()
        intent_data = {}

        def on_intent_classified(msg):
            intent_data.update(msg.get("facts", {}))
            received_intent.set()

        zooid = IntentZooid()
        zooid.start()

        try:
            intent_sub = UMNSub(
                "VOICE.INTENT.CLASSIFIED",
                on_intent_classified,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.STT.TRANSCRIPTION",
                ecosystem="voice",
                intensity=0.88,
                facts={
                    "text": "hello there",
                    "confidence": 0.88,
                    "language": "en-US"
                }
            )

            assert received_intent.wait(timeout=5.0), "Intent classification signal not received"

            assert intent_data["intent_type"] == "conversation"
            assert intent_data["command_type"] is None
            assert intent_data["confidence"] == 0.70

            intent_sub.close()
            pub.close()

        finally:
            zooid.shutdown()


@pytest.mark.integration
class TestSTTEmotionIntegration:
    """Test STT → Emotion Analysis signal coordination."""

    def test_transcription_to_emotion_flow(self, monkeypatch):
        """Test full flow: VOICE.STT.TRANSCRIPTION → VOICE.EMOTION.STATE."""
        monkeypatch.setenv("KLR_ENABLE_EMOTION", "1")

        received_emotion = threading.Event()
        emotion_data = {}

        def on_emotion_state(msg):
            """Callback for emotion state signal."""
            emotion_data.update(msg.get("facts", {}))
            received_emotion.set()

        zooid = EmotionZooid()
        zooid.start()

        try:
            emotion_sub = UMNSub(
                "VOICE.EMOTION.STATE",
                on_emotion_state,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.STT.TRANSCRIPTION",
                ecosystem="voice",
                intensity=0.95,
                facts={
                    "text": "this is wonderful and amazing!",
                    "confidence": 0.95,
                    "language": "en-US"
                },
                incident_id="emotion-test-001"
            )

            assert received_emotion.wait(timeout=5.0), "Emotion state signal not received"

            assert emotion_data["text"] == "this is wonderful and amazing!"
            assert emotion_data["sentiment"] == "positive"
            assert emotion_data["valence"] > 0.0
            assert emotion_data["confidence"] > 0.5

            emotion_sub.close()
            pub.close()

        finally:
            zooid.shutdown()

    def test_negative_emotion_detection(self, monkeypatch):
        """Test detection of negative emotion."""
        monkeypatch.setenv("KLR_ENABLE_EMOTION", "1")

        received_emotion = threading.Event()
        emotion_data = {}

        def on_emotion_state(msg):
            emotion_data.update(msg.get("facts", {}))
            received_emotion.set()

        zooid = EmotionZooid()
        zooid.start()

        try:
            emotion_sub = UMNSub(
                "VOICE.EMOTION.STATE",
                on_emotion_state,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.STT.TRANSCRIPTION",
                ecosystem="voice",
                intensity=0.90,
                facts={
                    "text": "this is terrible and awful",
                    "confidence": 0.90,
                    "language": "en-US"
                }
            )

            assert received_emotion.wait(timeout=5.0), "Emotion state signal not received"

            assert emotion_data["sentiment"] == "negative"
            assert emotion_data["valence"] < 0.0
            assert emotion_data["confidence"] > 0.5

            emotion_sub.close()
            pub.close()

        finally:
            zooid.shutdown()

    def test_neutral_emotion_detection(self, monkeypatch):
        """Test detection of neutral emotion."""
        monkeypatch.setenv("KLR_ENABLE_EMOTION", "1")

        received_emotion = threading.Event()
        emotion_data = {}

        def on_emotion_state(msg):
            emotion_data.update(msg.get("facts", {}))
            received_emotion.set()

        zooid = EmotionZooid()
        zooid.start()

        try:
            emotion_sub = UMNSub(
                "VOICE.EMOTION.STATE",
                on_emotion_state,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.STT.TRANSCRIPTION",
                ecosystem="voice",
                intensity=0.85,
                facts={
                    "text": "the sky is blue",
                    "confidence": 0.85,
                    "language": "en-US"
                }
            )

            assert received_emotion.wait(timeout=5.0), "Emotion state signal not received"

            assert emotion_data["sentiment"] == "neutral"
            assert emotion_data["valence"] == 0.0
            assert emotion_data["confidence"] == 0.5

            emotion_sub.close()
            pub.close()

        finally:
            zooid.shutdown()

    def test_emotional_shift_detection(self, monkeypatch):
        """Test detection of emotional shift."""
        monkeypatch.setenv("KLR_ENABLE_EMOTION", "1")

        received_shift = threading.Event()
        shift_data = {}

        def on_emotion_shift(msg):
            """Callback for emotion shift signal."""
            shift_data.update(msg.get("facts", {}))
            received_shift.set()

        zooid = EmotionZooid()
        zooid.start()

        try:
            shift_sub = UMNSub(
                "VOICE.EMOTION.SHIFT.DETECTED",
                on_emotion_shift,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()

            pub.emit(
                "VOICE.STT.TRANSCRIPTION",
                ecosystem="voice",
                intensity=0.90,
                facts={
                    "text": "this is terrible",
                    "confidence": 0.90
                }
            )

            time.sleep(0.5)

            pub.emit(
                "VOICE.STT.TRANSCRIPTION",
                ecosystem="voice",
                intensity=0.95,
                facts={
                    "text": "this is absolutely wonderful and amazing!",
                    "confidence": 0.95
                }
            )

            assert received_shift.wait(timeout=5.0), "Emotion shift signal not received"

            assert "previous_state" in shift_data
            assert "new_state" in shift_data
            assert shift_data["previous_state"]["valence"] < 0.0
            assert shift_data["new_state"]["valence"] > 0.0

            shift_sub.close()
            pub.close()

        finally:
            zooid.shutdown()


@pytest.mark.integration
class TestIntentEmotionCombined:
    """Test combined Intent + Emotion processing from single transcription."""

    def test_simultaneous_intent_and_emotion_processing(self, monkeypatch):
        """Test that both Intent and Emotion zooids process the same transcription."""
        monkeypatch.setenv("KLR_ENABLE_INTENT", "1")
        monkeypatch.setenv("KLR_ENABLE_EMOTION", "1")

        received_intent = threading.Event()
        received_emotion = threading.Event()
        intent_data = {}
        emotion_data = {}

        def on_intent_classified(msg):
            intent_data.update(msg.get("facts", {}))
            received_intent.set()

        def on_emotion_state(msg):
            emotion_data.update(msg.get("facts", {}))
            received_emotion.set()

        intent_zooid = IntentZooid()
        emotion_zooid = EmotionZooid()

        intent_zooid.start()
        emotion_zooid.start()

        try:
            intent_sub = UMNSub(
                "VOICE.INTENT.CLASSIFIED",
                on_intent_classified,
                zooid_name="test-orchestrator",
                niche="test"
            )

            emotion_sub = UMNSub(
                "VOICE.EMOTION.STATE",
                on_emotion_state,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.STT.TRANSCRIPTION",
                ecosystem="voice",
                intensity=0.95,
                facts={
                    "text": "what is my name?",
                    "confidence": 0.95,
                    "language": "en-US"
                },
                incident_id="combined-test-001"
            )

            assert received_intent.wait(timeout=5.0), "Intent classification not received"
            assert received_emotion.wait(timeout=5.0), "Emotion state not received"

            assert intent_data["text"] == "what is my name?"
            assert intent_data["intent_type"] == "command"
            assert intent_data["command_type"] == "identity"

            assert emotion_data["text"] == "what is my name?"
            assert emotion_data["dominance"] < 0.0

            intent_sub.close()
            emotion_sub.close()
            pub.close()

        finally:
            intent_zooid.shutdown()
            emotion_zooid.shutdown()


@pytest.mark.integration
class TestOrchestratorKnowledgeIntegration:
    """Test Orchestrator → Knowledge signal coordination (Phase 3)."""

    def test_orchestrator_knowledge_request_flow(self, monkeypatch):
        """Test full flow: VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST → VOICE.KNOWLEDGE.RESULTS."""
        monkeypatch.setenv("KLR_ENABLE_KNOWLEDGE", "1")

        received_results = threading.Event()
        knowledge_data = {}

        def on_knowledge_results(msg):
            """Callback for knowledge results signal."""
            knowledge_data.update(msg.get("facts", {}))
            received_results.set()

        from src.kloros_voice_knowledge import KnowledgeZooid
        zooid = KnowledgeZooid()
        zooid.start()

        try:
            results_sub = UMNSub(
                "VOICE.KNOWLEDGE.RESULTS",
                on_knowledge_results,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "query": "test query",
                    "top_k": 5,
                    "filters": {}
                },
                incident_id="knowledge-test-001"
            )

            assert received_results.wait(timeout=5.0), "Knowledge results signal not received"

            assert knowledge_data["query"] == "test query"
            assert knowledge_data["count"] == 0
            assert knowledge_data["documents"] == []
            assert knowledge_data["metadata"]["rag_available"] is False

            results_sub.close()
            pub.close()

        finally:
            zooid.shutdown()

    def test_knowledge_request_without_query(self, monkeypatch):
        """Test handling of knowledge request without query parameter."""
        monkeypatch.setenv("KLR_ENABLE_KNOWLEDGE", "1")

        received_error = threading.Event()
        error_data = {}

        def on_knowledge_error(msg):
            """Callback for knowledge error signal."""
            error_data.update(msg.get("facts", {}))
            received_error.set()

        from src.kloros_voice_knowledge import KnowledgeZooid
        zooid = KnowledgeZooid()
        zooid.start()

        try:
            error_sub = UMNSub(
                "VOICE.KNOWLEDGE.ERROR",
                on_knowledge_error,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "top_k": 5
                }
            )

            assert received_error.wait(timeout=5.0), "Knowledge error signal not received"

            assert error_data["error_type"] == "missing_query"

            error_sub.close()
            pub.close()

        finally:
            zooid.shutdown()

    def test_knowledge_request_with_custom_top_k(self, monkeypatch):
        """Test knowledge request with custom top_k parameter."""
        monkeypatch.setenv("KLR_ENABLE_KNOWLEDGE", "1")

        received_results = threading.Event()
        knowledge_data = {}

        def on_knowledge_results(msg):
            """Callback for knowledge results signal."""
            knowledge_data.update(msg.get("facts", {}))
            received_results.set()

        from src.kloros_voice_knowledge import KnowledgeZooid
        zooid = KnowledgeZooid()
        zooid.start()

        try:
            results_sub = UMNSub(
                "VOICE.KNOWLEDGE.RESULTS",
                on_knowledge_results,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "query": "custom query",
                    "top_k": 10,
                    "filters": {}
                }
            )

            assert received_results.wait(timeout=5.0), "Knowledge results signal not received"

            assert knowledge_data["query"] == "custom query"
            assert knowledge_data["count"] == 0
            assert knowledge_data["metadata"]["rag_available"] is False

            results_sub.close()
            pub.close()

        finally:
            zooid.shutdown()


@pytest.mark.integration
class TestOrchestratorLLMIntegration:
    """Test Orchestrator → LLM Integration signal coordination (Phase 4)."""

    def test_orchestrator_llm_request_flow(self, monkeypatch):
        """Test full flow: VOICE.ORCHESTRATOR.LLM.REQUEST → VOICE.LLM.RESPONSE."""
        monkeypatch.setenv("KLR_ENABLE_LLM", "1")

        received_response = threading.Event()
        llm_data = {}

        def on_llm_response(msg):
            """Callback for LLM response signal."""
            llm_data.update(msg.get("facts", {}))
            received_response.set()

        from src.kloros_voice_llm import LLMZooid
        zooid = LLMZooid()
        zooid.start()

        try:
            response_sub = UMNSub(
                "VOICE.LLM.RESPONSE",
                on_llm_response,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            from unittest.mock import patch, Mock
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"response": "Test LLM response"}

            pub = UMNPub()
            with patch('requests.post', return_value=mock_response):
                pub.emit(
                    "VOICE.ORCHESTRATOR.LLM.REQUEST",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "prompt": "test prompt for integration",
                        "mode": "non-streaming",
                        "temperature": 0.8
                    },
                    incident_id="llm-test-001"
                )

                assert received_response.wait(timeout=5.0), "LLM response signal not received"

            assert llm_data["response"] == "Test LLM response"
            assert llm_data["backend"] == "ollama"
            assert "latency" in llm_data

            response_sub.close()
            pub.close()

        finally:
            zooid.shutdown()

    def test_llm_request_with_error(self, monkeypatch):
        """Test LLM request error handling."""
        monkeypatch.setenv("KLR_ENABLE_LLM", "1")

        received_error = threading.Event()
        error_data = {}

        def on_llm_error(msg):
            """Callback for LLM error signal."""
            error_data.update(msg.get("facts", {}))
            received_error.set()

        from src.kloros_voice_llm import LLMZooid
        zooid = LLMZooid()
        zooid.start()

        try:
            error_sub = UMNSub(
                "VOICE.LLM.ERROR",
                on_llm_error,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            pub = UMNPub()
            pub.emit(
                "VOICE.ORCHESTRATOR.LLM.REQUEST",
                ecosystem="voice",
                intensity=1.0,
                facts={
                    "prompt": ""
                }
            )

            assert received_error.wait(timeout=5.0), "LLM error signal not received"

            assert error_data["error_type"] == "missing_prompt"

            error_sub.close()
            pub.close()

        finally:
            zooid.shutdown()

    def test_llm_request_with_custom_parameters(self, monkeypatch):
        """Test LLM request with custom parameters."""
        monkeypatch.setenv("KLR_ENABLE_LLM", "1")

        received_response = threading.Event()
        llm_data = {}

        def on_llm_response(msg):
            """Callback for LLM response signal."""
            llm_data.update(msg.get("facts", {}))
            received_response.set()

        from src.kloros_voice_llm import LLMZooid
        zooid = LLMZooid()
        zooid.start()

        try:
            response_sub = UMNSub(
                "VOICE.LLM.RESPONSE",
                on_llm_response,
                zooid_name="test-orchestrator",
                niche="test"
            )

            time.sleep(0.5)

            from unittest.mock import patch, Mock
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"response": "Custom response"}

            pub = UMNPub()
            with patch('requests.post', return_value=mock_response):
                pub.emit(
                    "VOICE.ORCHESTRATOR.LLM.REQUEST",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "prompt": "custom prompt",
                        "mode": "non-streaming",
                        "temperature": 0.9,
                        "max_tokens": 100,
                        "model": "custom_model"
                    }
                )

                assert received_response.wait(timeout=5.0), "LLM response signal not received"

            assert llm_data["response"] == "Custom response"
            assert llm_data["temperature"] == 0.9

            response_sub.close()
            pub.close()

        finally:
            zooid.shutdown()


# ============================================================================
# Orchestrator ↔ Session Integration Tests (Phase 5)
# ============================================================================

@pytest.mark.integration
class TestOrchestratorSessionIntegration:
    """Test Orchestrator → Session Management signal coordination (Phase 5).

    Note: These tests verify basic UMN connectivity and signal reception.
    Due to UMN message echoing and shared bus architecture, exact message
    counts may vary. The unit tests (test_voice_session.py) provide comprehensive
    validation of Session zooid functionality with mocked UMN.
    """

    def test_session_stt_transcription_flow(self, monkeypatch):
        """Test Session zooid receives and processes STT transcriptions."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("KLR_SESSION_PERSIST_DIR", tmpdir)

            from src.kloros_voice_session import SessionZooid
            zooid = SessionZooid()

            # Clear history before start to establish baseline
            zooid.start()
            initial_count = len(zooid.conversation_history)

            try:
                # Emit STT transcription signal
                pub = UMNPub()
                pub.emit(
                    "VOICE.STT.TRANSCRIPTION",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "text": "Integration test message",
                        "confidence": 0.95,
                        "timestamp": time.time()
                    }
                )

                time.sleep(0.5)  # Allow signal processing

                # Verify message was added to history (allow for UMN echoing)
                assert len(zooid.conversation_history) >= initial_count + 1
                # Find our message in the history
                found = any(
                    msg["role"] == "user" and
                    msg["content"] == "Integration test message"
                    for msg in zooid.conversation_history
                )
                assert found, "Expected message not found in conversation history"
                assert zooid.stats["user_messages"] >= 1

                pub.close()

            finally:
                zooid.shutdown()

    def test_session_llm_response_flow(self, monkeypatch):
        """Test Session zooid receives and processes LLM responses."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("KLR_SESSION_PERSIST_DIR", tmpdir)

            from src.kloros_voice_session import SessionZooid
            zooid = SessionZooid()
            zooid.start()
            initial_count = len(zooid.conversation_history)

            try:
                # Emit LLM response signal
                pub = UMNPub()
                pub.emit(
                    "VOICE.LLM.RESPONSE",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "response": "Integration test response",
                        "model": "qwen2.5:72b",
                        "backend": "remote",
                        "timestamp": time.time()
                    }
                )

                time.sleep(0.5)

                # Verify response was added to history (allow for UMN echoing)
                assert len(zooid.conversation_history) >= initial_count + 1
                # Find our message in the history
                found = any(
                    msg["role"] == "assistant" and
                    msg["content"] == "Integration test response"
                    for msg in zooid.conversation_history
                )
                assert found, "Expected response not found in conversation history"
                assert zooid.stats["assistant_messages"] >= 1

                pub.close()

            finally:
                zooid.shutdown()

    def test_session_full_conversation_flow(self, monkeypatch):
        """Test Session zooid tracks a complete conversation."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("KLR_SESSION_PERSIST_DIR", tmpdir)

            from src.kloros_voice_session import SessionZooid
            zooid = SessionZooid()

            # Track SESSION.UPDATED signals
            updated_count = {"count": 0}
            session_data = {}

            def on_session_updated(msg):
                updated_count["count"] += 1
                session_data.update(msg.get("facts", {}))

            session_sub = UMNSub(
                "VOICE.SESSION.UPDATED",
                on_session_updated,
                zooid_name="test-orchestrator",
                niche="test"
            )

            zooid.start()
            initial_count = len(zooid.conversation_history)

            try:
                pub = UMNPub()

                # User says something
                pub.emit(
                    "VOICE.STT.TRANSCRIPTION",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "text": "What is the capital of France?",
                        "confidence": 0.98,
                        "timestamp": time.time()
                    }
                )

                time.sleep(0.3)

                # Assistant responds
                pub.emit(
                    "VOICE.LLM.RESPONSE",
                    ecosystem="voice",
                    intensity=1.0,
                    facts={
                        "response": "The capital of France is Paris.",
                        "model": "main",
                        "backend": "ollama",
                        "timestamp": time.time()
                    }
                )

                time.sleep(0.3)

                # Verify conversation history (allow for UMN echoing)
                assert len(zooid.conversation_history) >= initial_count + 2
                # Find both messages in history
                found_user = any(
                    msg["role"] == "user" and
                    msg["content"] == "What is the capital of France?"
                    for msg in zooid.conversation_history
                )
                found_assistant = any(
                    msg["role"] == "assistant" and
                    msg["content"] == "The capital of France is Paris."
                    for msg in zooid.conversation_history
                )
                assert found_user, "User message not found in conversation history"
                assert found_assistant, "Assistant message not found in conversation history"
                assert zooid.stats["user_messages"] >= 1
                assert zooid.stats["assistant_messages"] >= 1

                # Verify SESSION.UPDATED signals were emitted
                assert updated_count["count"] >= 2
                assert session_data["message_count"] >= 2

                session_sub.close()
                pub.close()

            finally:
                zooid.shutdown()
