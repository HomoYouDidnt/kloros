"""
Vector store for KLoROS semantic memory using ChromaDB.

Provides efficient vector similarity search for semantic memory retrieval
with persistence, metadata filtering, and hybrid search capabilities.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    chromadb = None
    Settings = None
    HAS_CHROMADB = False

import numpy as np

from .embeddings import get_embedding_engine

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_on_db_error(func: Callable[..., T], max_retries: int = 3, backoff_ms: int = 100) -> Callable[..., T]:
    """
    Decorator to retry ChromaDB operations on transient disk I/O errors.

    Args:
        func: Function to wrap
        max_retries: Maximum number of retry attempts (default: 3)
        backoff_ms: Initial backoff delay in milliseconds (doubles each retry)

    Returns:
        Wrapped function with retry logic
    """
    def wrapper(*args, **kwargs) -> T:
        last_exception = None
        delay_ms = backoff_ms

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()

                # Only retry on transient disk I/O errors (SQLite error code 522)
                if 'disk i/o error' in error_msg or 'code: 522' in error_msg or 'database is locked' in error_msg:
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"[vector_store] Transient DB error (attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {delay_ms}ms..."
                        )
                        time.sleep(delay_ms / 1000.0)
                        delay_ms *= 2  # Exponential backoff
                        continue
                    else:
                        logger.error(f"[vector_store] DB error persisted after {max_retries} retries: {e}")

                # Non-transient error or max retries exceeded - raise immediately
                raise

        # Should not reach here, but raise last exception if we do
        if last_exception:
            raise last_exception

    return wrapper


class VectorStore:
    """
    ChromaDB-based vector store for semantic search.

    Features:
    - Persistent storage of embeddings
    - Fast similarity search with HNSW index
    - Metadata filtering
    - Hybrid search (semantic + keyword)
    - Batch operations
    """

    def __init__(
        self,
        persist_directory: Optional[Path] = None,
        collection_name: str = "kloros_memory"
    ):
        """
        Initialize vector store.

        Args:
            persist_directory: Directory for ChromaDB persistence
            collection_name: Name of the collection
        """
        if not HAS_CHROMADB:
            raise ImportError(
                "chromadb is not installed. "
                "Install it with: pip install chromadb"
            )

        self.persist_directory = persist_directory or Path("~/.kloros/vectordb").expanduser()
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}  # Cosine similarity
        )

        # Get embedding engine
        self.embedding_engine = get_embedding_engine()

        logger.info(f"[vector_store] Initialized collection '{collection_name}' with {self.collection.count()} embeddings")

    def add(
        self,
        text: str,
        doc_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[np.ndarray] = None
    ) -> None:
        """
        Add a document to the vector store.

        Args:
            text: Text content to embed
            doc_id: Unique document ID (event_id, episode_id, etc.)
            metadata: Optional metadata for filtering
            embedding: Pre-computed embedding (computes if None)
        """
        # Compute embedding if not provided
        if embedding is None:
            embedding = self.embedding_engine.embed(text)

        # Convert numpy array to list for ChromaDB
        embedding_list = embedding.tolist() if isinstance(embedding, np.ndarray) else embedding

        # Add to collection with retry on transient errors
        def _add_operation():
            return self.collection.add(
                embeddings=[embedding_list],
                documents=[text],
                ids=[str(doc_id)],
                metadatas=[metadata or {}]
            )

        retry_on_db_error(_add_operation)()

    def add_batch(
        self,
        texts: List[str],
        doc_ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        embeddings: Optional[List[np.ndarray]] = None
    ) -> None:
        """
        Add multiple documents in batch.

        Args:
            texts: List of text content
            doc_ids: List of unique document IDs
            metadatas: Optional list of metadata dicts
            embeddings: Pre-computed embeddings (computes if None)
        """
        if len(texts) != len(doc_ids):
            raise ValueError("texts and doc_ids must have same length")

        # Compute embeddings if not provided
        if embeddings is None:
            embeddings = self.embedding_engine.embed_batch(texts)

        # Convert to lists for ChromaDB
        embedding_lists = [
            emb.tolist() if isinstance(emb, np.ndarray) else emb
            for emb in embeddings
        ]

        # Prepare metadatas
        if metadatas is None:
            metadatas = [{} for _ in texts]

        # Add to collection with retry on transient errors
        def _add_batch_operation():
            return self.collection.add(
                embeddings=embedding_lists,
                documents=texts,
                ids=[str(doc_id) for doc_id in doc_ids],
                metadatas=metadatas
            )

        retry_on_db_error(_add_batch_operation)()

    def search(
        self,
        query: str,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
        min_similarity: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents.

        Args:
            query: Query text
            top_k: Number of results to return
            where: Metadata filters (e.g., {"event_type": "user_input"})
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of result dicts with keys: id, text, metadata, similarity
        """
        # Embed query
        query_embedding = self.embedding_engine.embed(query)
        query_embedding_list = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding

        # Search collection with retry on transient errors
        def _query_operation():
            return self.collection.query(
                query_embeddings=[query_embedding_list],
                n_results=top_k,
                where=where
            )

        results = retry_on_db_error(_query_operation)()

        # Format results
        formatted_results = []
        for i in range(len(results['ids'][0])):
            # ChromaDB returns distances (lower is more similar for cosine)
            # Convert to similarity score (1 - distance)
            distance = results['distances'][0][i]
            similarity = 1.0 - distance  # Cosine distance to similarity

            # Filter by minimum similarity
            if min_similarity is not None and similarity < min_similarity:
                continue

            formatted_results.append({
                'id': results['ids'][0][i],
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'similarity': similarity,
                'distance': distance
            })

        return formatted_results

    def search_by_embedding(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
        min_similarity: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search using pre-computed query embedding.

        Args:
            query_embedding: Query vector
            top_k: Number of results
            where: Metadata filters
            min_similarity: Minimum similarity threshold

        Returns:
            List of result dicts
        """
        query_embedding_list = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding

        results = self.collection.query(
            query_embeddings=[query_embedding_list],
            n_results=top_k,
            where=where
        )

        formatted_results = []
        for i in range(len(results['ids'][0])):
            distance = results['distances'][0][i]
            similarity = 1.0 - distance

            if min_similarity is not None and similarity < min_similarity:
                continue

            formatted_results.append({
                'id': results['ids'][0][i],
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'similarity': similarity,
                'distance': distance
            })

        return formatted_results

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document dict or None if not found
        """
        try:
            result = self.collection.get(
                ids=[str(doc_id)],
                include=["embeddings", "documents", "metadatas"]
            )

            if result['ids']:
                return {
                    'id': result['ids'][0],
                    'text': result['documents'][0],
                    'metadata': result['metadatas'][0],
                    'embedding': result['embeddings'][0]
                }
        except Exception as e:
            logger.error(f"[vector_store] Error retrieving {doc_id}: {e}")

        return None

    def delete(self, doc_id: str) -> bool:
        """
        Delete a document by ID.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            self.collection.delete(ids=[str(doc_id)])
            return True
        except Exception as e:
            logger.error(f"[vector_store] Error deleting {doc_id}: {e}")
            return False

    def delete_batch(self, doc_ids: List[str]) -> int:
        """
        Delete multiple documents.

        Args:
            doc_ids: List of document IDs

        Returns:
            Number of documents deleted
        """
        try:
            self.collection.delete(ids=[str(doc_id) for doc_id in doc_ids])
            return len(doc_ids)
        except Exception as e:
            logger.error(f"[vector_store] Error deleting batch: {e}")
            return 0

    def update_metadata(self, doc_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Update document metadata.

        Args:
            doc_id: Document ID
            metadata: New metadata

        Returns:
            True if updated, False otherwise
        """
        try:
            self.collection.update(
                ids=[str(doc_id)],
                metadatas=[metadata]
            )
            return True
        except Exception as e:
            logger.error(f"[vector_store] Error updating metadata for {doc_id}: {e}")
            return False

    def count(self) -> int:
        """Get number of documents in store."""
        return self.collection.count()

    def clear(self) -> None:
        """Clear all documents from the store."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"[vector_store] Cleared collection '{self.collection_name}'")

    def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics."""
        return {
            "collection_name": self.collection_name,
            "document_count": self.count(),
            "persist_directory": str(self.persist_directory),
            "embedding_dim": self.embedding_engine.embedding_dim,
            "model_name": self.embedding_engine.model_name
        }


# Global vector store instance
_vector_store: Optional[VectorStore] = None


def get_vector_store(
    collection_name: Optional[str] = None,
    force_reload: bool = False
) -> Optional['VectorStore']:
    """
    Get or create global vector store instance.

    Checks SSOT configuration to determine backend (ChromaDB or Qdrant).

    Args:
        collection_name: Collection name (default: kloros_memory)
        force_reload: Force reload of store

    Returns:
        VectorStore instance (ChromaDB or Qdrant) or None if backend not available
    """
    global _vector_store

    backend = os.getenv("KLR_VECTOR_BACKEND", None)

    if backend is None:
        try:
            import tomllib
            config_path = Path("/home/kloros/config/models.toml")
            if config_path.exists():
                with open(config_path, "rb") as f:
                    config = tomllib.load(f)
                backend = config.get("vector_store", {}).get("backend", "chromadb")
            else:
                backend = "chromadb"
        except Exception:
            backend = "chromadb"

    if backend == "qdrant":
        try:
            from kloros_memory.vector_store_qdrant import get_qdrant_vector_store
            logger.info("[vector_store] Using Qdrant backend")
            return get_qdrant_vector_store(collection_name=collection_name, force_reload=force_reload)
        except ImportError as e:
            logger.warning(f"[vector_store] Qdrant backend requested but not available: {e}, falling back to ChromaDB")
            backend = "chromadb"

    if not HAS_CHROMADB:
        logger.warning("[vector_store] chromadb not installed, vector store disabled")
        return None

    if _vector_store is None or force_reload:
        collection_name = collection_name or os.getenv("KLR_VECTOR_COLLECTION", "kloros_memory")
        try:
            _vector_store = VectorStore(collection_name=collection_name)
            logger.info("[vector_store] Using ChromaDB backend")
        except Exception as e:
            logger.error(f"[vector_store] Failed to create vector store: {e}")
            return None

    return _vector_store
