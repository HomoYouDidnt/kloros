"""
Vector store for KLoROS semantic memory using Qdrant.

Drop-in replacement for ChromaDB with better stability, lower memory usage,
and no dimension locking. Preserves exact API compatibility.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        VectorParams,
        PointStruct,
        Filter,
        FieldCondition,
        MatchValue,
        SearchParams,
    )
    HAS_QDRANT = True
except ImportError:
    QdrantClient = None
    HAS_QDRANT = False

import numpy as np

from .embeddings import get_embedding_engine

try:
    from src.orchestration.core.umn_bus import UMNPub as ChemPub
    HAS_CHEMBUS = True
except ImportError:
    ChemPub = None
    HAS_CHEMBUS = False

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """
    Qdrant-based vector store for semantic search.

    Features:
    - Persistent storage with better stability than ChromaDB
    - Lower memory usage (mmap, quantization)
    - No dimension locking issues
    - Fast similarity search with HNSW index
    - Metadata filtering via payloads
    - Batch operations
    - Drop-in replacement for ChromaDB VectorStore
    """

    def __init__(
        self,
        persist_directory: Optional[Path] = None,
        collection_name: str = "kloros_memory",
        server_url: Optional[str] = None
    ):
        """
        Initialize vector store.

        Args:
            persist_directory: Directory for Qdrant persistence (file mode only)
            collection_name: Name of the collection
            server_url: Qdrant server URL (e.g., "http://localhost:6333") for server mode
        """
        if not HAS_QDRANT:
            raise ImportError(
                "qdrant-client is not installed. "
                "Install it with: pip install qdrant-client"
            )

        self.collection_name = collection_name

        # Server mode or file mode?
        if server_url:
            logger.info(f"[qdrant] Using server mode: {server_url}")
            self.client = QdrantClient(url=server_url)
            self.persist_directory = None
        else:
            self.persist_directory = persist_directory or Path("~/.kloros/vectordb_qdrant").expanduser()
            self.persist_directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"[qdrant] Using file mode: {self.persist_directory}")
            self.client = QdrantClient(path=str(self.persist_directory))

        self.embedding_engine = get_embedding_engine()
        embedding_dim = self.embedding_engine.embedding_dim

        if not self.client.collection_exists(collection_name):
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"[qdrant] Created collection '{collection_name}' with {embedding_dim}-dim vectors")
        else:
            logger.info(f"[qdrant] Using existing collection '{collection_name}'")

        count = self.count()
        logger.info(f"[qdrant] Initialized collection '{collection_name}' with {count} embeddings")

        # Initialize ChemBus publisher for operation signals
        self.chem_pub = ChemPub() if HAS_CHEMBUS else None
        if self.chem_pub:
            logger.debug("[qdrant] ChemBus signal emission enabled")

    def _doc_id_to_uuid(self, doc_id: str) -> str:
        """Convert document ID to deterministic UUID string."""
        import hashlib
        from uuid import UUID
        doc_id_hash = hashlib.sha256(doc_id.encode()).digest()
        return str(UUID(bytes=doc_id_hash[:16]))

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
        start_time = time.time()

        if embedding is None:
            embedding = self.embedding_engine.embed(text)

        embedding_list = embedding.tolist() if isinstance(embedding, np.ndarray) else embedding

        payload = metadata or {}
        payload["_text"] = text
        payload["_doc_id"] = doc_id  # Store original doc_id

        # Convert doc_id to UUID (Qdrant requires UUID or int)
        point_id = self._doc_id_to_uuid(doc_id)

        point = PointStruct(
            id=point_id,
            vector=embedding_list,
            payload=payload
        )

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )

        # Emit ChemBus signal
        latency_ms = (time.time() - start_time) * 1000
        if self.chem_pub:
            self.chem_pub.emit(
                signal="Q_MEMORY_WRITE",
                ecosystem="memory",
                facts={
                    "collection": self.collection_name,
                    "doc_id": doc_id,
                    "has_metadata": bool(metadata),
                    "text_length": len(text),
                    "latency_ms": round(latency_ms, 2)
                }
            )

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
        start_time = time.time()

        if len(texts) != len(doc_ids):
            raise ValueError("texts and doc_ids must have same length")

        if embeddings is None:
            embeddings = self.embedding_engine.embed_batch(texts)

        if metadatas is None:
            metadatas = [{} for _ in texts]

        points = []
        for text, doc_id, metadata, embedding in zip(texts, doc_ids, metadatas, embeddings):
            embedding_list = embedding.tolist() if isinstance(embedding, np.ndarray) else embedding

            payload = metadata.copy()
            payload["_text"] = text
            payload["_doc_id"] = doc_id  # Store original doc_id

            # Convert doc_id to UUID (Qdrant requires UUID or int)
            point_id = self._doc_id_to_uuid(doc_id)

            points.append(PointStruct(
                id=point_id,
                vector=embedding_list,
                payload=payload
            ))

        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

        # Emit ChemBus signal
        latency_ms = (time.time() - start_time) * 1000
        if self.chem_pub:
            self.chem_pub.emit(
                signal="Q_MEMORY_BATCH_WRITE",
                ecosystem="memory",
                facts={
                    "collection": self.collection_name,
                    "batch_size": len(texts),
                    "latency_ms": round(latency_ms, 2)
                }
            )

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
        query_embedding = self.embedding_engine.embed(query)
        return self.search_by_embedding(
            query_embedding=query_embedding,
            top_k=top_k,
            where=where,
            min_similarity=min_similarity
        )

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
        start_time = time.time()

        query_embedding_list = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding

        query_filter = None
        if where:
            conditions = []
            for key, value in where.items():
                conditions.append(
                    FieldCondition(key=key, match=MatchValue(value=value))
                )
            if conditions:
                query_filter = Filter(must=conditions)

        score_threshold = None
        if min_similarity is not None:
            score_threshold = min_similarity

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding_list,
            limit=top_k,
            query_filter=query_filter,
            score_threshold=score_threshold,
            with_payload=True
        )

        formatted_results = []
        for hit in results:
            payload = hit.payload.copy()
            text = payload.pop("_text", "")

            similarity = hit.score
            distance = 1.0 - similarity

            formatted_results.append({
                'id': hit.id,
                'text': text,
                'metadata': payload,
                'similarity': similarity,
                'distance': distance
            })

        # Emit ChemBus signal
        latency_ms = (time.time() - start_time) * 1000
        if self.chem_pub:
            self.chem_pub.emit(
                signal="Q_MEMORY_SEARCH",
                ecosystem="memory",
                facts={
                    "collection": self.collection_name,
                    "top_k": top_k,
                    "results_count": len(formatted_results),
                    "has_filters": bool(where),
                    "min_similarity": min_similarity,
                    "latency_ms": round(latency_ms, 2)
                }
            )

        return formatted_results

    def get(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a document by ID.

        Args:
            doc_id: Document ID (original doc_id, will be converted to UUID)

        Returns:
            Document dict or None if not found
        """
        try:
            # Convert doc_id to UUID (same as add/add_batch)
            point_id = self._doc_id_to_uuid(doc_id)

            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[point_id],
                with_vectors=True,
                with_payload=True
            )

            if points:
                point = points[0]
                payload = point.payload.copy()
                text = payload.pop("_text", "")
                original_doc_id = payload.pop("_doc_id", doc_id)

                return {
                    'id': original_doc_id,  # Return original doc_id, not UUID
                    'text': text,
                    'metadata': payload,
                    'embedding': point.vector
                }
        except Exception as e:
            logger.error(f"[qdrant] Error retrieving {doc_id}: {e}")

        return None

    def delete(self, doc_id: str) -> bool:
        """
        Delete a document by ID.

        Args:
            doc_id: Document ID (original doc_id, will be converted to UUID)

        Returns:
            True if deleted, False otherwise
        """
        try:
            point_id = self._doc_id_to_uuid(doc_id)
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[point_id]
            )
            return True
        except Exception as e:
            logger.error(f"[qdrant] Error deleting {doc_id}: {e}")
            return False

    def delete_batch(self, doc_ids: List[str]) -> int:
        """
        Delete multiple documents.

        Args:
            doc_ids: List of document IDs (original doc_ids, will be converted to UUIDs)

        Returns:
            Number of documents deleted
        """
        start_time = time.time()
        try:
            point_ids = [self._doc_id_to_uuid(doc_id) for doc_id in doc_ids]
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=point_ids
            )
            deleted_count = len(doc_ids)

            # Emit ChemBus signal
            latency_ms = (time.time() - start_time) * 1000
            if self.chem_pub:
                self.chem_pub.emit(
                    signal="Q_MEMORY_DELETE",
                    ecosystem="memory",
                    facts={
                        "collection": self.collection_name,
                        "delete_count": deleted_count,
                        "latency_ms": round(latency_ms, 2)
                    }
                )

            return deleted_count
        except Exception as e:
            logger.error(f"[qdrant] Error deleting batch: {e}")
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
            existing = self.get(doc_id)
            if not existing:
                return False

            new_payload = metadata.copy()
            new_payload["_text"] = existing["text"]

            self.client.set_payload(
                collection_name=self.collection_name,
                payload=new_payload,
                points=[doc_id]
            )
            return True
        except Exception as e:
            logger.error(f"[qdrant] Error updating metadata for {doc_id}: {e}")
            return False

    def count(self) -> int:
        """Get number of documents in store."""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return collection_info.points_count or 0
        except Exception:
            return 0

    def clear(self) -> None:
        """Clear all documents from the store."""
        try:
            self.client.delete_collection(self.collection_name)
            embedding_dim = self.embedding_engine.embedding_dim
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"[qdrant] Cleared collection '{self.collection_name}'")
        except Exception as e:
            logger.error(f"[qdrant] Error clearing collection: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics."""
        return {
            "collection_name": self.collection_name,
            "document_count": self.count(),
            "persist_directory": str(self.persist_directory),
            "embedding_dim": self.embedding_engine.embedding_dim,
            "model_name": self.embedding_engine.model_name,
            "backend": "qdrant"
        }


_qdrant_vector_store: Optional[QdrantVectorStore] = None


def get_qdrant_vector_store(
    collection_name: Optional[str] = None,
    force_reload: bool = False
) -> Optional['QdrantVectorStore']:
    """
    Get or create global Qdrant vector store instance.

    Reads server URL from models.toml config. If server_url is provided,
    uses server mode (concurrent access). Otherwise uses file mode (single process).

    Args:
        collection_name: Collection name (default: kloros_memory)
        force_reload: Force reload of store

    Returns:
        QdrantVectorStore instance or None if qdrant-client is not available
    """
    global _qdrant_vector_store

    if not HAS_QDRANT:
        logger.warning("[qdrant] qdrant-client not installed, vector store disabled")
        return None

    if _qdrant_vector_store is None or force_reload:
        collection_name = collection_name or os.getenv("KLR_VECTOR_COLLECTION", "kloros_memory")

        # Read server URL from config
        server_url = os.getenv("KLR_QDRANT_URL", None)
        if server_url is None:
            try:
                import tomllib
                config_path = Path("/home/kloros/config/models.toml")
                if config_path.exists():
                    with open(config_path, "rb") as f:
                        config = tomllib.load(f)
                    server_url = config.get("vector_store", {}).get("server_url", None)
            except Exception as e:
                logger.debug(f"[qdrant] Could not read config: {e}")

        try:
            _qdrant_vector_store = QdrantVectorStore(
                collection_name=collection_name,
                server_url=server_url
            )
        except Exception as e:
            logger.error(f"[qdrant] Failed to create vector store: {e}")
            return None

    return _qdrant_vector_store
