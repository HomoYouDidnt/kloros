"""Unit tests for Knowledge zooid - test in isolation with mocked UMN."""
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.fixtures.umn_mock import MockUMNPub, MockUMNSub
from src.kloros_voice_knowledge import KnowledgeZooid


@pytest.fixture
def zooid(monkeypatch):
    """Create KnowledgeZooid with mocked dependencies."""
    monkeypatch.setenv("KLR_ENABLE_KNOWLEDGE", "1")

    with patch('src.kloros_voice_knowledge.UMNPub', MockUMNPub), \
         patch('src.kloros_voice_knowledge.UMNSub', MockUMNSub), \
         patch('src.kloros_voice_knowledge._RAGClass', None):

        zooid = KnowledgeZooid()
        yield zooid

        zooid.shutdown()


class TestKnowledgeZooidInit:
    """Test KnowledgeZooid initialization."""

    def test_init_sets_zooid_name(self, zooid):
        """Test that zooid name is set correctly."""
        assert zooid.zooid_name == "kloros-voice-knowledge"
        assert zooid.niche == "voice.knowledge"

    def test_init_statistics(self, zooid):
        """Test that statistics are initialized."""
        assert zooid.stats["total_queries"] == 0
        assert zooid.stats["successful_queries"] == 0
        assert zooid.stats["failed_queries"] == 0
        assert zooid.stats["average_relevance"] == 0.0
        assert zooid.stats["query_times"] == []

    def test_init_rag_not_available(self, zooid):
        """Test initialization with no RAG backend."""
        assert zooid.rag_available is False
        assert zooid.rag is None

    def test_init_environment_variables(self, zooid):
        """Test that environment variables are read."""
        assert zooid.enable_knowledge == 1
        assert zooid.default_top_k == 5


class TestKnowledgeZooidStart:
    """Test KnowledgeZooid startup."""

    def test_start_emits_ready_signal(self, zooid):
        """Test that start() emits VOICE.KNOWLEDGE.READY signal."""
        zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.KNOWLEDGE.READY") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.KNOWLEDGE.READY")
        assert msg is not None
        assert msg.ecosystem == "voice"
        assert msg.facts["zooid"] == "kloros-voice-knowledge"
        assert msg.facts["rag_available"] is False
        assert msg.facts["backend"] == "none"

    def test_start_subscribes_to_knowledge_request(self, zooid):
        """Test that start() subscribes to VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST."""
        zooid.start()

        assert hasattr(zooid, 'knowledge_request_sub')
        assert zooid.knowledge_request_sub.topic == "VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST"

    def test_start_disabled_knowledge(self, monkeypatch):
        """Test that Knowledge can be disabled via environment."""
        monkeypatch.setenv("KLR_ENABLE_KNOWLEDGE", "0")

        with patch('src.kloros_voice_knowledge.UMNPub', MockUMNPub), \
             patch('src.kloros_voice_knowledge.UMNSub', MockUMNSub), \
             patch('src.kloros_voice_knowledge._RAGClass', None):
            zooid = KnowledgeZooid()
            zooid.start()

        assert zooid.chem_pub.get_signal_count("VOICE.KNOWLEDGE.READY") == 0


class TestRAGBackendInitialization:
    """Test RAG backend initialization."""

    def test_rag_not_available_no_module(self, monkeypatch):
        """Test RAG unavailable when module not imported."""
        monkeypatch.setenv("KLR_ENABLE_KNOWLEDGE", "1")

        with patch('src.kloros_voice_knowledge.UMNPub', MockUMNPub), \
             patch('src.kloros_voice_knowledge.UMNSub', MockUMNSub), \
             patch('src.kloros_voice_knowledge._RAGClass', None):
            zooid = KnowledgeZooid()
            zooid.start()

        assert zooid.rag_available is False
        assert zooid.rag is None

    def test_rag_bundle_path_missing(self, monkeypatch, tmp_path):
        """Test RAG unavailable when bundle path doesn't exist."""
        monkeypatch.setenv("KLR_ENABLE_KNOWLEDGE", "1")
        monkeypatch.setenv("KLR_RAG_BUNDLE_PATH", "/nonexistent/bundle.npz")

        mock_rag_class = Mock()

        with patch('src.kloros_voice_knowledge.UMNPub', MockUMNPub), \
             patch('src.kloros_voice_knowledge.UMNSub', MockUMNSub), \
             patch('src.kloros_voice_knowledge._RAGClass', mock_rag_class):
            zooid = KnowledgeZooid()
            zooid.start()

        assert zooid.rag_available is False
        assert zooid.rag is None
        mock_rag_class.assert_not_called()

    def test_rag_bundle_path_exists(self, monkeypatch, tmp_path):
        """Test RAG initialization with valid bundle path."""
        bundle_path = tmp_path / "bundle.npz"
        bundle_path.write_text("dummy")

        monkeypatch.setenv("KLR_ENABLE_KNOWLEDGE", "1")
        monkeypatch.setenv("KLR_RAG_BUNDLE_PATH", str(bundle_path))

        mock_rag_class = Mock()
        mock_rag_instance = Mock()
        mock_rag_class.return_value = mock_rag_instance

        with patch('src.kloros_voice_knowledge.UMNPub', MockUMNPub), \
             patch('src.kloros_voice_knowledge.UMNSub', MockUMNSub), \
             patch('src.kloros_voice_knowledge._RAGClass', mock_rag_class):
            zooid = KnowledgeZooid()
            zooid.start()

        assert zooid.rag_available is True
        assert zooid.rag is mock_rag_instance
        mock_rag_class.assert_called_once_with(bundle_path=str(bundle_path))

    def test_rag_metadata_embeddings_paths(self, monkeypatch, tmp_path):
        """Test RAG initialization with metadata and embeddings paths."""
        metadata_path = tmp_path / "metadata.json"
        embeddings_path = tmp_path / "embeddings.npy"
        metadata_path.write_text("{}")
        embeddings_path.write_text("dummy")

        monkeypatch.setenv("KLR_ENABLE_KNOWLEDGE", "1")
        monkeypatch.setenv("KLR_RAG_METADATA_PATH", str(metadata_path))
        monkeypatch.setenv("KLR_RAG_EMBEDDINGS_PATH", str(embeddings_path))

        mock_rag_class = Mock()
        mock_rag_instance = Mock()
        mock_rag_class.return_value = mock_rag_instance

        with patch('src.kloros_voice_knowledge.UMNPub', MockUMNPub), \
             patch('src.kloros_voice_knowledge.UMNSub', MockUMNSub), \
             patch('src.kloros_voice_knowledge._RAGClass', mock_rag_class):
            zooid = KnowledgeZooid()
            zooid.start()

        assert zooid.rag_available is True
        assert zooid.rag is mock_rag_instance
        mock_rag_class.assert_called_once_with(
            metadata_path=str(metadata_path),
            embeddings_path=str(embeddings_path)
        )


class TestKnowledgeRetrieval:
    """Test knowledge retrieval functionality."""

    def test_perform_retrieval_rag_unavailable(self, zooid):
        """Test retrieval with no RAG backend."""
        results = zooid._perform_retrieval("test query", 5, {})

        assert results["documents"] == []
        assert results["relevance_scores"] == []
        assert results["sources"] == []

    def test_perform_retrieval_with_search_method(self, zooid):
        """Test retrieval when RAG has search() method."""
        mock_rag = Mock()
        mock_rag.search.return_value = [
            {"text": "doc1", "score": 0.9, "source": {"file": "f1"}},
            {"text": "doc2", "score": 0.8, "source": {"file": "f2"}}
        ]
        zooid.rag = mock_rag
        zooid.rag_available = True

        results = zooid._perform_retrieval("test query", 2, {})

        assert len(results["documents"]) == 2
        assert results["documents"][0] == "doc1"
        assert results["documents"][1] == "doc2"
        assert results["relevance_scores"][0] == 0.9
        assert results["relevance_scores"][1] == 0.8
        assert results["sources"][0] == {"file": "f1"}

    def test_perform_retrieval_with_query_method(self, zooid):
        """Test retrieval when RAG has query() method."""
        mock_rag = Mock()
        delattr(mock_rag, 'search')
        mock_rag.query.return_value = {
            "documents": ["doc1", "doc2"],
            "scores": [0.9, 0.8],
            "sources": [{"file": "f1"}, {"file": "f2"}]
        }
        zooid.rag = mock_rag
        zooid.rag_available = True

        results = zooid._perform_retrieval("test query", 2, {})

        assert results["documents"] == ["doc1", "doc2"]
        assert results["relevance_scores"] == [0.9, 0.8]
        assert results["sources"] == [{"file": "f1"}, {"file": "f2"}]

    def test_perform_retrieval_tuple_format(self, zooid):
        """Test retrieval with tuple-format results."""
        mock_rag = Mock()
        mock_rag.search.return_value = [
            ("doc1", 0.9, {"file": "f1"}),
            ("doc2", 0.8, {"file": "f2"})
        ]
        zooid.rag = mock_rag
        zooid.rag_available = True

        results = zooid._perform_retrieval("test query", 2, {})

        assert results["documents"] == ["doc1", "doc2"]
        assert results["relevance_scores"] == [0.9, 0.8]
        assert results["sources"] == [{"file": "f1"}, {"file": "f2"}]

    def test_perform_retrieval_limits_top_k(self, zooid):
        """Test that retrieval respects top_k limit."""
        mock_rag = Mock()
        mock_rag.search.return_value = [
            {"text": f"doc{i}", "score": 0.9 - i * 0.1, "source": {}}
            for i in range(10)
        ]
        zooid.rag = mock_rag
        zooid.rag_available = True

        results = zooid._perform_retrieval("test query", 3, {})

        assert len(results["documents"]) == 3
        assert len(results["relevance_scores"]) == 3


class TestKnowledgeSignalEmission:
    """Test UMN signal emission for knowledge retrieval."""

    def test_on_knowledge_request_emits_results(self, zooid):
        """Test that knowledge request handler emits VOICE.KNOWLEDGE.RESULTS."""
        zooid.rag_available = False
        zooid.start()

        zooid._on_knowledge_request({
            "facts": {
                "query": "test query",
                "top_k": 5,
                "filters": {}
            },
            "incident_id": "knowledge-001"
        })

        assert zooid.chem_pub.get_signal_count("VOICE.KNOWLEDGE.RESULTS") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.KNOWLEDGE.RESULTS")
        assert msg.facts["query"] == "test query"
        assert msg.facts["count"] == 0
        assert msg.facts["documents"] == []
        assert msg.incident_id == "knowledge-001"

    def test_on_knowledge_request_with_results(self, zooid):
        """Test knowledge request with actual results."""
        zooid.start()

        mock_rag = Mock()
        mock_rag.search.return_value = [
            {"text": "doc1", "score": 0.9, "source": {"file": "f1"}}
        ]
        zooid.rag = mock_rag
        zooid.rag_available = True

        zooid._on_knowledge_request({
            "facts": {
                "query": "test query",
                "top_k": 5
            }
        })

        assert zooid.chem_pub.get_signal_count("VOICE.KNOWLEDGE.RESULTS") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.KNOWLEDGE.RESULTS")
        assert msg.facts["count"] == 1
        assert msg.facts["documents"][0] == "doc1"
        assert msg.facts["relevance_scores"][0] == 0.9

    def test_on_knowledge_request_missing_query(self, zooid):
        """Test handling of missing query in request."""
        zooid.start()

        zooid._on_knowledge_request({
            "facts": {
                "top_k": 5
            }
        })

        assert zooid.chem_pub.get_signal_count("VOICE.KNOWLEDGE.ERROR") == 1
        assert zooid.chem_pub.get_signal_count("VOICE.KNOWLEDGE.RESULTS") == 0

    def test_on_knowledge_request_updates_statistics(self, zooid):
        """Test that knowledge request updates statistics."""
        zooid.rag_available = False
        zooid.start()

        initial_total = zooid.stats["total_queries"]

        zooid._on_knowledge_request({
            "facts": {
                "query": "test query",
                "top_k": 5
            }
        })

        assert zooid.stats["total_queries"] == initial_total + 1
        assert zooid.stats["successful_queries"] == 1


class TestKnowledgeStatistics:
    """Test Knowledge statistics tracking."""

    def test_get_stats(self, zooid):
        """Test getting Knowledge statistics."""
        stats = zooid.get_stats()

        assert "total_queries" in stats
        assert "successful_queries" in stats
        assert "failed_queries" in stats
        assert "average_relevance" in stats
        assert "average_query_time" in stats
        assert "rag_available" in stats

    def test_statistics_count_correctly(self, zooid):
        """Test that statistics count queries correctly."""
        zooid.rag_available = False
        zooid.start()

        zooid._on_knowledge_request({"facts": {"query": "query1", "top_k": 5}})
        zooid._on_knowledge_request({"facts": {"query": "query2", "top_k": 5}})
        zooid._on_knowledge_request({"facts": {"query": "query3", "top_k": 5}})

        stats = zooid.get_stats()
        assert stats["total_queries"] == 3
        assert stats["successful_queries"] == 3
        assert stats["failed_queries"] == 0

    def test_statistics_track_query_times(self, zooid):
        """Test that query times are tracked."""
        zooid.rag_available = False
        zooid.start()

        zooid._on_knowledge_request({"facts": {"query": "query1", "top_k": 5}})

        assert len(zooid.stats["query_times"]) == 1
        assert zooid.stats["query_times"][0] > 0

    def test_statistics_limit_query_times_history(self, zooid):
        """Test that query times history is limited to 100."""
        zooid.rag_available = False
        zooid.start()

        for i in range(150):
            zooid._on_knowledge_request({"facts": {"query": f"query{i}", "top_k": 5}})

        assert len(zooid.stats["query_times"]) == 100


class TestKnowledgeZooidShutdown:
    """Test KnowledgeZooid shutdown."""

    def test_shutdown_emits_signal(self, zooid):
        """Test that shutdown emits VOICE.KNOWLEDGE.SHUTDOWN signal."""
        zooid.start()
        zooid.shutdown()

        assert zooid.chem_pub.get_signal_count("VOICE.KNOWLEDGE.SHUTDOWN") == 1
        msg = zooid.chem_pub.get_last_message("VOICE.KNOWLEDGE.SHUTDOWN")
        assert "stats" in msg.facts

    def test_shutdown_stops_processing(self, zooid):
        """Test that shutdown stops processing."""
        zooid.start()
        zooid.shutdown()

        assert not zooid.running

        zooid._on_knowledge_request({
            "facts": {
                "query": "test query",
                "top_k": 5
            }
        })

        assert zooid.chem_pub.get_signal_count("VOICE.KNOWLEDGE.RESULTS") == 0
