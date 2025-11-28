"""Conversation logging adapter for Qdrant episodic memory.

Drop-in replacement for ChromaDB ConversationLogger with better stability.
"""
import time
import uuid
import hashlib
import logging
from typing import Dict, Any, List, Optional
from uuid import UUID

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        VectorParams,
        PointStruct,
        Filter,
        FieldCondition,
        MatchValue,
        Range,
        ScrollRequest,
    )
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False
    QdrantClient = None

from kloros_memory.embeddings import get_embedding_engine

logger = logging.getLogger(__name__)


class QdrantConversationLogger:
    """Logs conversations to Qdrant for hybrid semantic + keyword retrieval."""

    def __init__(self, client: QdrantClient, collection_prefix: str = "kloros"):
        """Initialize conversation logger.

        Args:
            client: Qdrant client instance
            collection_prefix: Prefix for collection names (default: kloros)
        """
        if not HAS_QDRANT:
            raise ImportError("qdrant-client is required for QdrantConversationLogger")

        self.client = client
        self.collection_prefix = collection_prefix

        self.conversations_collection = f"{collection_prefix}_conversations"
        self.tool_calls_collection = f"{collection_prefix}_tool_calls"
        self.episodes_collection = f"{collection_prefix}_episodes"

        self.current_episode_id = None
        self.turn_counter = 0

        self.embedding_engine = get_embedding_engine()
        embedding_dim = self.embedding_engine.embedding_dim

        self._init_collections(embedding_dim)

        from .bm25_index import BM25ConversationIndex
        self.bm25_index = BM25ConversationIndex()
        self._rebuild_bm25_index()

    def _init_collections(self, embedding_dim: int):
        """Initialize Qdrant collections."""
        collections = [
            (self.conversations_collection, "Conversation turns (user/system)"),
            (self.tool_calls_collection, "Tool invocations and results"),
            (self.episodes_collection, "Episode summaries and context")
        ]

        for collection_name, description in collections:
            if not self.client.collection_exists(collection_name):
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"[qdrant_conv] Created collection '{collection_name}'")
            else:
                logger.debug(f"[qdrant_conv] Using existing collection '{collection_name}'")

    def _doc_id_to_uuid(self, doc_id: str) -> str:
        """Convert document ID to deterministic UUID string."""
        doc_id_hash = hashlib.sha256(doc_id.encode()).digest()
        return str(UUID(bytes=doc_id_hash[:16]))

    def start_episode(self, initial_context: str = ""):
        """Start a new conversation episode.

        Args:
            initial_context: Optional context for the episode

        Returns:
            Episode ID (UUID)
        """
        self.current_episode_id = str(uuid.uuid4())
        self.turn_counter = 0

        if initial_context:
            point_id = self._doc_id_to_uuid(f"ep:{self.current_episode_id}")
            embedding = self.embedding_engine.embed(initial_context)
            embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

            payload = {
                "episode_id": self.current_episode_id,
                "ts": time.time(),
                "turn_count": 0,
                "_text": initial_context,
                "_doc_id": f"ep:{self.current_episode_id}"
            }

            point = PointStruct(
                id=point_id,
                vector=embedding_list,
                payload=payload
            )

            self.client.upsert(
                collection_name=self.episodes_collection,
                points=[point]
            )

        return self.current_episode_id

    def log_turn(self, user_query: str, system_response: str,
                 tool_used: Optional[str] = None,
                 tool_result: Optional[str] = None,
                 metadata: Optional[Dict[str, Any]] = None):
        """Log a single conversation turn.

        Args:
            user_query: User's input query
            system_response: KLoROS's response
            tool_used: Name of tool invoked (if any)
            tool_result: Tool execution result summary
            metadata: Additional metadata (e.g., latency, tokens)
        """
        if self.current_episode_id is None:
            self.start_episode()

        self.turn_counter += 1
        turn_id = f"turn:{self.current_episode_id}:{self.turn_counter}"
        ts = time.time()

        query_doc = f"User: {user_query}"
        query_meta = {
            "episode_id": self.current_episode_id,
            "turn": self.turn_counter,
            "speaker": "user",
            "ts": ts,
            "tool_used": tool_used or "none",
            "_text": query_doc,
            "_doc_id": f"{turn_id}:query"
        }
        if metadata:
            query_meta.update(metadata)

        query_embedding = self.embedding_engine.embed(query_doc)
        query_embedding_list = query_embedding.tolist() if hasattr(query_embedding, 'tolist') else list(query_embedding)

        query_point = PointStruct(
            id=self._doc_id_to_uuid(f"{turn_id}:query"),
            vector=query_embedding_list,
            payload=query_meta
        )

        self.client.upsert(
            collection_name=self.conversations_collection,
            points=[query_point]
        )

        self.bm25_index.add_documents([{
            'id': f"{turn_id}:query",
            'document': query_doc,
            'metadata': query_meta
        }])

        response_doc = f"KLoROS: {system_response}"
        response_meta = {
            "episode_id": self.current_episode_id,
            "turn": self.turn_counter,
            "speaker": "system",
            "ts": ts,
            "tool_used": tool_used or "none",
            "_text": response_doc,
            "_doc_id": f"{turn_id}:response"
        }
        if metadata:
            response_meta.update(metadata)

        response_embedding = self.embedding_engine.embed(response_doc)
        response_embedding_list = response_embedding.tolist() if hasattr(response_embedding, 'tolist') else list(response_embedding)

        response_point = PointStruct(
            id=self._doc_id_to_uuid(f"{turn_id}:response"),
            vector=response_embedding_list,
            payload=response_meta
        )

        self.client.upsert(
            collection_name=self.conversations_collection,
            points=[response_point]
        )

        self.bm25_index.add_documents([{
            'id': f"{turn_id}:response",
            'document': response_doc,
            'metadata': response_meta
        }])

        if tool_used and tool_result:
            tool_doc = f"Tool: {tool_used}\nResult: {tool_result}"
            tool_meta = {
                "episode_id": self.current_episode_id,
                "turn": self.turn_counter,
                "tool": tool_used,
                "ts": ts,
                "_text": tool_doc,
                "_doc_id": f"{turn_id}:tool"
            }

            tool_embedding = self.embedding_engine.embed(tool_doc)
            tool_embedding_list = tool_embedding.tolist() if hasattr(tool_embedding, 'tolist') else list(tool_embedding)

            tool_point = PointStruct(
                id=self._doc_id_to_uuid(f"{turn_id}:tool"),
                vector=tool_embedding_list,
                payload=tool_meta
            )

            self.client.upsert(
                collection_name=self.tool_calls_collection,
                points=[tool_point]
            )

    def _rebuild_bm25_index(self):
        """Rebuild BM25 index from existing Qdrant documents."""
        try:
            scroll_result = self.client.scroll(
                collection_name=self.conversations_collection,
                limit=10000,
                with_payload=True,
                with_vectors=False
            )

            if scroll_result and scroll_result[0]:
                documents = []
                for point in scroll_result[0]:
                    if '_text' in point.payload and '_doc_id' in point.payload:
                        documents.append({
                            'id': point.payload['_doc_id'],
                            'document': point.payload['_text'],
                            'metadata': {k: v for k, v in point.payload.items()
                                       if k not in ['_text', '_doc_id']}
                        })

                if documents:
                    self.bm25_index.add_documents(documents)
                    logger.info(f"[bm25] Indexed {len(documents)} documents from Qdrant")
        except Exception as e:
            logger.warning(f"[bm25] Failed to rebuild index: {e}")

    def retrieve_context(self, query: str, k: int = 5,
                        time_window_hours: Optional[float] = None,
                        use_hybrid: bool = True) -> List[Dict[str, Any]]:
        """Retrieve relevant conversation context using hybrid search.

        Args:
            query: Query to find relevant context for
            k: Number of results to retrieve
            time_window_hours: Optional time window in hours (recent memory priority)
            use_hybrid: Use hybrid BM25 + vector search (default True)

        Returns:
            List of relevant conversation turns with metadata
        """
        query_filter = None

        if time_window_hours:
            cutoff_ts = time.time() - (time_window_hours * 3600)
            query_filter = Filter(
                must=[FieldCondition(
                    key="ts",
                    range=Range(gte=cutoff_ts)
                )]
            )

        collection_info = self.client.get_collection(self.conversations_collection)
        collection_count = collection_info.points_count or 0

        if collection_count == 0:
            return []

        if not use_hybrid:
            query_embedding = self.embedding_engine.embed(query)
            query_embedding_list = query_embedding.tolist() if hasattr(query_embedding, 'tolist') else list(query_embedding)

            results = self.client.search(
                collection_name=self.conversations_collection,
                query_vector=query_embedding_list,
                limit=min(k, collection_count),
                query_filter=query_filter,
                with_payload=True
            )

            context_items = []
            for hit in results:
                payload = hit.payload.copy()
                text = payload.pop("_text", "")
                doc_id = payload.pop("_doc_id", str(hit.id))

                context_items.append({
                    'id': doc_id,
                    'document': text,
                    'metadata': payload,
                    'distance': 1.0 - hit.score  # Qdrant returns cosine similarity, convert to distance
                })

            return context_items

        query_embedding = self.embedding_engine.embed(query)
        query_embedding_list = query_embedding.tolist() if hasattr(query_embedding, 'tolist') else list(query_embedding)

        vector_results = self.client.search(
            collection_name=self.conversations_collection,
            query_vector=query_embedding_list,
            limit=min(k * 2, collection_count),
            query_filter=query_filter,
            with_payload=True
        )

        vector_items = []
        for hit in vector_results:
            payload = hit.payload.copy()
            text = payload.pop("_text", "")
            doc_id = payload.pop("_doc_id", str(hit.id))

            vector_items.append({
                'id': doc_id,
                'document': text,
                'metadata': payload,
                'distance': 1.0 - hit.score
            })

        bm25_items = self.bm25_index.search(query, k=k * 2)

        if not vector_items and not bm25_items:
            return []

        if not vector_items:
            return bm25_items[:k]
        if not bm25_items:
            return vector_items[:k]

        from src.rag.rrf_fusion import reciprocal_rank_fusion

        vector_ids = [item['id'] for item in vector_items]
        bm25_ids = [item['id'] for item in bm25_items]

        fused_scores = reciprocal_rank_fusion(vector_ids, bm25_ids, k=60)

        items_by_id = {item['id']: item for item in vector_items + bm25_items}
        merged_results = []

        for doc_id, score in sorted(fused_scores.items(), key=lambda x: x[1], reverse=True):
            if doc_id in items_by_id:
                doc = items_by_id[doc_id].copy()
                doc['rrf_score'] = score
                doc['distance'] = 1.0 / (1.0 + score)
                merged_results.append(doc)

        return merged_results[:k]

    def get_recent_turns(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get the N most recent conversation turns.

        Args:
            n: Number of recent turns to retrieve

        Returns:
            List of recent conversation turns
        """
        if not self.current_episode_id:
            return []

        query_filter = Filter(
            must=[FieldCondition(
                key="episode_id",
                match=MatchValue(value=self.current_episode_id)
            )]
        )

        scroll_result = self.client.scroll(
            collection_name=self.conversations_collection,
            scroll_filter=query_filter,
            limit=n * 2,
            with_payload=True,
            with_vectors=False
        )

        if not scroll_result or not scroll_result[0]:
            return []

        items = []
        for point in scroll_result[0]:
            payload = point.payload.copy()
            text = payload.pop("_text", "")
            doc_id = payload.pop("_doc_id", str(point.id))

            items.append({
                'id': doc_id,
                'document': text,
                'metadata': payload
            })

        items.sort(key=lambda x: (x['metadata'].get('turn', 0), x['id']), reverse=True)

        return items[:n]

    def finalize_episode(self, summary: str = ""):
        """Finalize the current episode with optional summary.

        Args:
            summary: Optional episode summary
        """
        if not self.current_episode_id:
            return

        if summary:
            point_id = self._doc_id_to_uuid(f"ep:{self.current_episode_id}")
            embedding = self.embedding_engine.embed(summary)
            embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

            payload = {
                "episode_id": self.current_episode_id,
                "ts": time.time(),
                "turn_count": self.turn_counter,
                "finalized": True,
                "_text": summary,
                "_doc_id": f"ep:{self.current_episode_id}"
            }

            point = PointStruct(
                id=point_id,
                vector=embedding_list,
                payload=payload
            )

            self.client.upsert(
                collection_name=self.episodes_collection,
                points=[point]
            )

        self.current_episode_id = None
        self.turn_counter = 0

    def count(self) -> int:
        """Get total number of conversation turns logged."""
        try:
            collection_info = self.client.get_collection(self.conversations_collection)
            return collection_info.points_count or 0
        except Exception:
            return 0
