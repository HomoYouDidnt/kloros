"""
Tests for knowledge_indexer LLM integration (Phase 4.2 & 4.3).

Verifies that knowledge_indexer:
- Uses LLMRouter instead of hardcoded AltimitOS endpoint
- Has fallback to text extraction when LLM unavailable
- Removes all hardcoded 100.67.244.66 references
- Properly integrates with local Ollama instances
"""

import logging
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

try:
    from qdrant_client import QdrantClient
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False

if HAS_QDRANT:
    from kloros_memory.knowledge_indexer import KnowledgeIndexer, get_knowledge_indexer
    from reasoning.llm_router import LLMMode


@pytest.mark.skipif(not HAS_QDRANT, reason="qdrant-client not installed")
class TestKnowledgeIndexerLLMIntegration:
    """Test knowledge_indexer integration with LLMRouter."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_qdrant = Mock(spec=QdrantClient)
        self.mock_qdrant.collection_exists.return_value = True

        self.mock_embedder = Mock()
        self.mock_embedder.embedding_dim = 384
        self.mock_embedder.embed.return_value = [0.1] * 384

    @patch("kloros_memory.knowledge_indexer.get_embedding_engine")
    @patch("kloros_memory.knowledge_indexer.get_router")
    def test_indexer_uses_llm_router(self, mock_get_router, mock_get_embedder):
        """KnowledgeIndexer should use LLMRouter instead of hardcoded endpoint."""
        mock_get_embedder.return_value = self.mock_embedder
        mock_router = Mock()
        mock_get_router.return_value = mock_router

        indexer = KnowledgeIndexer(
            qdrant_client=self.mock_qdrant,
            collection_name="test_collection"
        )

        assert indexer.router is mock_router, "KnowledgeIndexer should store router instance"

    @patch("kloros_memory.knowledge_indexer.get_embedding_engine")
    @patch("kloros_memory.knowledge_indexer.get_router")
    def test_generate_summary_uses_router(self, mock_get_router, mock_get_embedder):
        """_generate_summary should use router.query instead of hardcoded endpoint."""
        mock_get_embedder.return_value = self.mock_embedder
        mock_router = Mock()
        mock_router.query.return_value = (True, "Test summary", "local:ollama-live")
        mock_get_router.return_value = mock_router

        indexer = KnowledgeIndexer(
            qdrant_client=self.mock_qdrant,
            collection_name="test_collection"
        )

        summary = indexer._generate_summary(
            Path("/test/file.md"),
            "Test content",
            "markdown_doc"
        )

        mock_router.query.assert_called_once()
        call_args = mock_router.query.call_args
        assert call_args[1]["mode"] == LLMMode.LIVE
        assert call_args[1]["prefer_remote"] is False
        assert summary == "Test summary"

    @patch("kloros_memory.knowledge_indexer.get_embedding_engine")
    @patch("kloros_memory.knowledge_indexer.get_router")
    def test_fallback_when_llm_fails(self, mock_get_router, mock_get_embedder):
        """Should use fallback summary when LLM query fails."""
        mock_get_embedder.return_value = self.mock_embedder
        mock_router = Mock()
        mock_router.query.return_value = (False, "Connection error", "error")
        mock_get_router.return_value = mock_router

        indexer = KnowledgeIndexer(
            qdrant_client=self.mock_qdrant,
            collection_name="test_collection"
        )

        long_content = "A" * 1000
        summary = indexer._generate_summary(
            Path("/test/file.md"),
            long_content,
            "markdown_doc"
        )

        assert len(summary) <= 503
        assert summary.endswith("...")

    @patch("kloros_memory.knowledge_indexer.get_embedding_engine")
    @patch("kloros_memory.knowledge_indexer.get_router")
    def test_fallback_on_exception(self, mock_get_router, mock_get_embedder):
        """Should use fallback summary when LLM raises exception."""
        mock_get_embedder.return_value = self.mock_embedder
        mock_router = Mock()
        mock_router.query.side_effect = Exception("Router unavailable")
        mock_get_router.return_value = mock_router

        indexer = KnowledgeIndexer(
            qdrant_client=self.mock_qdrant,
            collection_name="test_collection"
        )

        content = "Test content for fallback"
        summary = indexer._generate_summary(
            Path("/test/file.md"),
            content,
            "markdown_doc"
        )

        assert summary == content
        assert "Test content for fallback" in summary

    @patch("kloros_memory.knowledge_indexer.get_embedding_engine")
    @patch("kloros_memory.knowledge_indexer.get_router")
    def test_no_hardcoded_endpoint_initialization(self, mock_get_router, mock_get_embedder):
        """KnowledgeIndexer init should not accept llm_url parameter."""
        mock_get_embedder.return_value = self.mock_embedder
        mock_router = Mock()
        mock_get_router.return_value = mock_router

        indexer = KnowledgeIndexer(
            qdrant_client=self.mock_qdrant,
            collection_name="test_collection"
        )

        assert not hasattr(indexer, "llm_url"), \
            "KnowledgeIndexer should not store hardcoded llm_url"
        assert not hasattr(indexer, "llm_model"), \
            "KnowledgeIndexer should not store llm_model"

    def test_fallback_summary_extraction(self):
        """_fallback_summary should extract first N characters."""
        mock_get_embedder = Mock()
        mock_get_embedder.embedding_dim = 384
        mock_router = Mock()

        with patch("kloros_memory.knowledge_indexer.get_embedding_engine", return_value=mock_get_embedder):
            with patch("kloros_memory.knowledge_indexer.get_router", return_value=mock_router):
                indexer = KnowledgeIndexer(
                    qdrant_client=self.mock_qdrant,
                    collection_name="test_collection"
                )

                content = "A" * 1000
                summary = indexer._fallback_summary(content, max_chars=100)

                assert len(summary) == 103
                assert summary == "A" * 100 + "..."

    def test_fallback_summary_short_content(self):
        """_fallback_summary should not add ellipsis for short content."""
        mock_get_embedder = Mock()
        mock_get_embedder.embedding_dim = 384
        mock_router = Mock()

        with patch("kloros_memory.knowledge_indexer.get_embedding_engine", return_value=mock_get_embedder):
            with patch("kloros_memory.knowledge_indexer.get_router", return_value=mock_router):
                indexer = KnowledgeIndexer(
                    qdrant_client=self.mock_qdrant,
                    collection_name="test_collection"
                )

                content = "Short"
                summary = indexer._fallback_summary(content, max_chars=100)

                assert summary == "Short"
                assert "..." not in summary


@pytest.mark.skipif(not HAS_QDRANT, reason="qdrant-client not installed")
class TestGetKnowledgeIndexer:
    """Test get_knowledge_indexer factory function."""

    @patch("kloros_memory.knowledge_indexer.get_qdrant_vector_store")
    @patch("kloros_memory.knowledge_indexer.get_embedding_engine")
    @patch("kloros_memory.knowledge_indexer.get_router")
    def test_factory_no_llm_parameters(self, mock_get_router, mock_get_embedder, mock_get_store):
        """get_knowledge_indexer should not accept LLM parameters."""
        mock_embedder = Mock()
        mock_embedder.embedding_dim = 384
        mock_get_embedder.return_value = mock_embedder
        mock_router = Mock()
        mock_get_router.return_value = mock_router

        mock_qdrant = Mock(spec=QdrantClient)
        mock_qdrant.collection_exists.return_value = True
        mock_store = Mock()
        mock_store.client = mock_qdrant
        mock_get_store.return_value = mock_store

        indexer = get_knowledge_indexer(collection_name="test")

        assert indexer is not None
        assert isinstance(indexer, KnowledgeIndexer)

    @patch("kloros_memory.knowledge_indexer.get_qdrant_vector_store")
    @patch("kloros_memory.knowledge_indexer.get_embedding_engine")
    @patch("kloros_memory.knowledge_indexer.get_router")
    def test_factory_uses_llm_router(self, mock_get_router, mock_get_embedder, mock_get_store):
        """get_knowledge_indexer should use LLMRouter."""
        mock_embedder = Mock()
        mock_embedder.embedding_dim = 384
        mock_get_embedder.return_value = mock_embedder
        mock_router = Mock()
        mock_get_router.return_value = mock_router

        mock_qdrant = Mock(spec=QdrantClient)
        mock_qdrant.collection_exists.return_value = True
        mock_store = Mock()
        mock_store.client = mock_qdrant
        mock_get_store.return_value = mock_store

        indexer = get_knowledge_indexer()

        mock_get_router.assert_called()
        assert indexer.router is mock_router


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
