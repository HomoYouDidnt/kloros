"""Conversation logging adapter for ChromaDB episodic memory."""
import time
import uuid
from typing import Dict, Any, List, Optional


class ConversationLogger:
    """Logs conversations to ChromaDB for hybrid semantic + keyword retrieval."""

    def __init__(self, client, collections):
        """Initialize conversation logger.

        Args:
            client: ChromaDB PersistentClient
            collections: Dictionary of ChromaDB collections
        """
        self.client = client
        self.conversations = collections['conversations']
        self.tool_calls = collections['tool_calls']
        self.episodes = collections['episodes']
        self.current_episode_id = None
        self.turn_counter = 0

        # Initialize BM25 index for keyword search
        from .bm25_index import BM25ConversationIndex
        self.bm25_index = BM25ConversationIndex()
        self._rebuild_bm25_index()

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
            self.episodes.upsert(
                ids=[f"ep:{self.current_episode_id}"],
                documents=[initial_context],
                metadatas=[{
                    "episode_id": self.current_episode_id,
                    "ts": time.time(),
                    "turn_count": 0
                }]
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

        # Log user query
        query_doc = f"User: {user_query}"
        query_meta = {
            "episode_id": self.current_episode_id,
            "turn": self.turn_counter,
            "speaker": "user",
            "ts": ts,
            "tool_used": tool_used or "none"
        }
        if metadata:
            query_meta.update(metadata)

        self.conversations.upsert(
            ids=[f"{turn_id}:query"],
            documents=[query_doc],
            metadatas=[query_meta]
        )

        # Add to BM25 index
        self.bm25_index.add_documents([{
            'id': f"{turn_id}:query",
            'document': query_doc,
            'metadata': query_meta
        }])

        # Log system response
        response_doc = f"KLoROS: {system_response}"
        response_meta = {
            "episode_id": self.current_episode_id,
            "turn": self.turn_counter,
            "speaker": "system",
            "ts": ts,
            "tool_used": tool_used or "none"
        }
        if metadata:
            response_meta.update(metadata)

        self.conversations.upsert(
            ids=[f"{turn_id}:response"],
            documents=[response_doc],
            metadatas=[response_meta]
        )

        # Add to BM25 index
        self.bm25_index.add_documents([{
            'id': f"{turn_id}:response",
            'document': response_doc,
            'metadata': response_meta
        }])

        # Log tool call if present
        if tool_used and tool_result:
            tool_doc = f"Tool: {tool_used}\nResult: {tool_result}"
            tool_meta = {
                "episode_id": self.current_episode_id,
                "turn": self.turn_counter,
                "tool": tool_used,
                "ts": ts
            }

            self.tool_calls.upsert(
                ids=[f"{turn_id}:tool"],
                documents=[tool_doc],
                metadatas=[tool_meta]
            )

    def _rebuild_bm25_index(self):
        """Rebuild BM25 index from existing ChromaDB documents."""
        try:
            # Get all documents from ChromaDB
            all_docs = self.conversations.get()
            if all_docs and all_docs['ids']:
                documents = []
                for i in range(len(all_docs['ids'])):
                    documents.append({
                        'id': all_docs['ids'][i],
                        'document': all_docs['documents'][i],
                        'metadata': all_docs['metadatas'][i]
                    })
                self.bm25_index.add_documents(documents)
                print(f"[bm25] Indexed {len(documents)} documents")
        except Exception as e:
            print(f"[bm25] Failed to rebuild index: {e}")

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
        where_filter = {}

        # Optional time window filtering
        if time_window_hours:
            cutoff_ts = time.time() - (time_window_hours * 3600)
            where_filter["ts"] = {"$gte": cutoff_ts}

        if not use_hybrid:
            # Vector-only search (original behavior)
            # Check if collection is empty first to avoid ChromaDB errors
            collection_count = self.conversations.count()
            if collection_count == 0:
                return []  # No data to query

            results = self.conversations.query(
                query_texts=[query],
                n_results=min(k, collection_count),  # Don't request more than available
                where=where_filter if where_filter else None
            )

            # Format results
            context_items = []
            if results and results['ids']:
                for i in range(len(results['ids'][0])):
                    context_items.append({
                        'id': results['ids'][0][i],
                        'document': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i] if 'distances' in results else None
                    })

            return context_items

        # Hybrid search: Vector + BM25 with RRF fusion
        # 1. Vector search
        # Check if collection is empty first to avoid ChromaDB errors
        collection_count = self.conversations.count()
        if collection_count == 0:
            return []  # No data to query

        vector_results = self.conversations.query(
            query_texts=[query],
            n_results=min(k * 2, collection_count),  # Don't request more than available
            where=where_filter if where_filter else None
        )

        vector_items = []
        if vector_results and vector_results['ids']:
            for i in range(len(vector_results['ids'][0])):
                vector_items.append({
                    'id': vector_results['ids'][0][i],
                    'document': vector_results['documents'][0][i],
                    'metadata': vector_results['metadatas'][0][i],
                    'distance': vector_results['distances'][0][i] if 'distances' in vector_results else None
                })

        # 2. BM25 search
        bm25_items = self.bm25_index.search(query, k=k * 2)

        # If both searches returned nothing, return empty
        if not vector_items and not bm25_items:
            return []

        # If only one search has results, return those
        if not vector_items:
            return bm25_items[:k]
        if not bm25_items:
            return vector_items[:k]

        # 3. Merge with RRF
        from src.rag.rrf_fusion import reciprocal_rank_fusion

        # Extract IDs for RRF
        vector_ids = [item['id'] for item in vector_items]
        bm25_ids = [item['id'] for item in bm25_items]

        # Fuse rankings
        fused_scores = reciprocal_rank_fusion(vector_ids, bm25_ids, k=60)

        # Create merged results with original metadata
        items_by_id = {item['id']: item for item in vector_items + bm25_items}
        merged_results = []

        for doc_id, score in sorted(fused_scores.items(), key=lambda x: x[1], reverse=True):
            if doc_id in items_by_id:
                doc = items_by_id[doc_id].copy()
                # Convert RRF score to distance-like metric (lower is better)
                # RRF scores are typically 0.01-0.05, so invert for consistency
                doc['rrf_score'] = score
                doc['distance'] = 1.0 / (1.0 + score)  # Normalized distance
                merged_results.append(doc)

        # Return top k
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

        # ChromaDB doesn't have direct "get latest N" - use peek or query with time filter
        # For now, use a simple implementation
        all_docs = self.conversations.get(
            where={"episode_id": self.current_episode_id},
            limit=n * 2  # Query + response pairs
        )

        if not all_docs or not all_docs['ids']:
            return []

        # Sort by turn number (descending) and return latest
        items = []
        for i in range(len(all_docs['ids'])):
            items.append({
                'id': all_docs['ids'][i],
                'document': all_docs['documents'][i],
                'metadata': all_docs['metadatas'][i]
            })

        # Sort by turn, then by query/response
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
            self.episodes.update(
                ids=[f"ep:{self.current_episode_id}"],
                documents=[summary],
                metadatas=[{
                    "episode_id": self.current_episode_id,
                    "ts": time.time(),
                    "turn_count": self.turn_counter,
                    "finalized": True
                }]
            )

        self.current_episode_id = None
        self.turn_counter = 0
