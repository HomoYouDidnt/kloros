"""
Smart context retrieval with scoring for KLoROS episodic memory.

Retrieves relevant context from memory using multiple scoring factors
including recency, importance, semantic similarity, and conversation relevance.
"""

from __future__ import annotations

import hashlib
import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import (
    Event,
    EpisodeSummary,
    EventType,
    ContextRetrievalRequest,
    ContextRetrievalResult
)
from .storage import MemoryStore
from .vector_store import get_vector_store
from .embeddings import get_embedding_engine
from .decay import DecayEngine


class ContextRetriever:
    """
    Smart context retrieval system for KLoROS memory.

    Features:
    - Multi-factor scoring (recency, importance, relevance)
    - Token budget management
    - Conversation awareness
    - Adaptive retrieval strategies
    """

    def __init__(self, store: Optional[MemoryStore] = None, enable_semantic: bool = True, enable_decay: bool = True):
        """
        Initialize the context retriever.

        Args:
            store: Memory storage instance
            enable_semantic: Enable semantic search (default: True)
            enable_decay: Enable decay filtering (default: True)
        """
        self.store = store or MemoryStore()

        # Scoring weights (can be tuned via environment)
        self.recency_weight = 0.3
        self.importance_weight = 0.4
        self.relevance_weight = 0.3

        # Time decay parameters
        self.recency_half_life_hours = 24.0  # Score halves every 24 hours
        self.max_age_days = 30  # Don't retrieve content older than 30 days

        # Phase 1: Semantic search
        self.enable_semantic = enable_semantic
        if self.enable_semantic:
            try:
                self.vector_store = get_vector_store()
                self.embedding_engine = get_embedding_engine()
            except Exception as e:
                import logging
                logging.warning(f"[retriever] Failed to initialize semantic search: {e}")
                self.enable_semantic = False

        # Phase 2: Memory decay
        self.enable_decay = enable_decay
        self.min_decay_score = 0.1  # Minimum decay score for retrieval
        if self.enable_decay:
            try:
                self.decay_engine = DecayEngine(store=self.store)
            except Exception as e:
                import logging
                logging.warning(f"[retriever] Failed to initialize decay engine: {e}")
                self.enable_decay = False

    def retrieve_context(self, request: ContextRetrievalRequest) -> ContextRetrievalResult:
        """
        Retrieve relevant context based on the request.

        Args:
            request: Context retrieval parameters

        Returns:
            Retrieved context with metadata
        """
        query_hash = hashlib.md5(request.query.encode()).hexdigest()[:12]
        start_time = time.time()

        # Calculate time window
        if request.time_window_hours:
            time_cutoff = time.time() - (request.time_window_hours * 3600)
        else:
            time_cutoff = time.time() - (self.max_age_days * 86400)

        # Retrieve candidate events
        candidate_events = self._get_candidate_events(
            conversation_id=request.conversation_id,
            time_cutoff=time_cutoff,
            limit=request.max_events * 3  # Get more candidates for better selection
        )

        # Retrieve candidate summaries
        candidate_summaries = self._get_candidate_summaries(
            min_importance=request.min_importance,
            time_cutoff=time_cutoff,
            limit=request.max_summaries * 2
        )

        # Phase 2: Filter by decay score
        if self.enable_decay:
            candidate_events = self._filter_by_decay(candidate_events)
            candidate_summaries = self._filter_summaries_by_decay(candidate_summaries)

        # Score and rank events
        scored_events = self._score_events(candidate_events, request.query)
        top_events = sorted(scored_events, key=lambda x: x[1], reverse=True)[:request.max_events]

        # Score and rank summaries
        scored_summaries = self._score_summaries(candidate_summaries, request.query)
        top_summaries = sorted(scored_summaries, key=lambda x: x[1], reverse=True)[:request.max_summaries]

        # Extract just the objects (remove scores)
        selected_events = [event for event, _ in top_events]
        selected_summaries = [summary for summary, _ in top_summaries]

        # Phase 2: Refresh decay for accessed memories
        if self.enable_decay:
            for event in selected_events:
                if event.id:
                    self.decay_engine.update_event_decay(event.id, refresh=True)

        # Calculate total token count
        total_tokens = self._calculate_total_tokens(selected_events, selected_summaries)

        # Create result
        result = ContextRetrievalResult(
            events=selected_events,
            summaries=selected_summaries,
            total_tokens=total_tokens,
            retrieval_time=time.time() - start_time,
            query_hash=query_hash
        )

        return result

    def semantic_search(
        self,
        query: str,
        top_k: int = 10,
        min_similarity: float = 0.5,
        conversation_id: Optional[str] = None
    ) -> List[Event]:
        """
        Perform semantic search for relevant events.

        Args:
            query: Natural language query
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold (0-1)
            conversation_id: Optional conversation filter

        Returns:
            List of relevant events, ordered by semantic similarity
        """
        if not self.enable_semantic:
            # Fallback to keyword search
            return self._get_candidate_events(
                conversation_id=conversation_id,
                time_cutoff=0,
                limit=top_k
            )

        # Build metadata filter
        where = {}
        if conversation_id:
            where["conversation_id"] = conversation_id

        # Search vector store
        results = self.vector_store.search(
            query=query,
            top_k=top_k,
            where=where if where else None,
            min_similarity=min_similarity
        )

        # Convert to Event objects
        events = []
        for result in results:
            # Extract event ID from doc_id (format: "event_<id>")
            doc_id = result['id']
            if doc_id.startswith("event_"):
                event_id = int(doc_id.split("_")[1])
                # Fetch full event from SQLite
                event = self.store.get_event(event_id)
                if event:
                    events.append(event)

        return events

    def _get_candidate_events(
        self,
        conversation_id: Optional[str],
        time_cutoff: float,
        limit: int
    ) -> List[Event]:
        """Get candidate events for context retrieval with fallback."""
        # Try conversation-specific retrieval first
        events = self.store.get_events(
            conversation_id=conversation_id,
            start_time=time_cutoff,
            limit=limit
        )

        # Fallback: If no events found and conversation_id was specified,
        # retrieve recent events without conversation filter
        if not events and conversation_id:
            events = self.store.get_events(
                conversation_id=None,  # No filter - get all recent
                start_time=time_cutoff,
                limit=limit
            )

        return events

    def _get_candidate_summaries(
        self,
        min_importance: float,
        time_cutoff: float,
        limit: int
    ) -> List[EpisodeSummary]:
        """Get candidate summaries for context retrieval."""
        # Get summaries with minimum importance
        summaries = self.store.get_summaries(
            min_importance=min_importance,
            limit=limit
        )

        # Filter by time cutoff
        filtered_summaries = [
            s for s in summaries
            if s.created_at >= time_cutoff
        ]

        return filtered_summaries

    def _filter_by_decay(self, events: List[Event]) -> List[Event]:
        """
        Filter events by decay score.

        Args:
            events: Events to filter

        Returns:
            Events with sufficient decay score
        """
        filtered = []
        conn = self.store._get_connection()

        for event in events:
            if not event.id:
                continue

            # Get decay score from database
            cursor = conn.execute(
                "SELECT decay_score FROM events WHERE id = ?",
                (event.id,)
            )
            row = cursor.fetchone()

            if row and row['decay_score']:
                if row['decay_score'] >= self.min_decay_score:
                    filtered.append(event)
            else:
                # No decay score yet, include by default
                filtered.append(event)

        return filtered

    def _filter_summaries_by_decay(self, summaries: List[EpisodeSummary]) -> List[EpisodeSummary]:
        """
        Filter summaries by decay score.

        Args:
            summaries: Summaries to filter

        Returns:
            Summaries with sufficient decay score
        """
        filtered = []
        conn = self.store._get_connection()

        for summary in summaries:
            if not summary.id:
                continue

            # Get decay score from database
            cursor = conn.execute(
                "SELECT decay_score FROM episode_summaries WHERE id = ?",
                (summary.id,)
            )
            row = cursor.fetchone()

            if row and row['decay_score']:
                if row['decay_score'] >= self.min_decay_score:
                    filtered.append(summary)
            else:
                # No decay score yet, include by default
                filtered.append(summary)

        return filtered

    def _score_events(self, events: List[Event], query: str) -> List[Tuple[Event, float]]:
        """
        Score events based on relevance, recency, and other factors.

        Args:
            events: Events to score
            query: Query for relevance scoring

        Returns:
            List of (event, score) tuples
        """
        scored_events = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for event in events:
            # Recency score (exponential decay)
            recency_score = self._calculate_recency_score(event.timestamp)

            # Relevance score (keyword matching)
            relevance_score = self._calculate_text_relevance(
                event.content.lower(),
                query_lower,
                query_words
            )

            # Event type importance
            type_score = self._get_event_type_importance(event.event_type)

            # Confidence boost
            confidence_score = event.confidence if event.confidence else 0.5

            # Combined score
            combined_score = (
                self.recency_weight * recency_score +
                self.relevance_weight * relevance_score +
                0.2 * type_score +
                0.1 * confidence_score
            )

            scored_events.append((event, combined_score))

        return scored_events

    def _score_summaries(
        self,
        summaries: List[EpisodeSummary],
        query: str
    ) -> List[Tuple[EpisodeSummary, float]]:
        """
        Score summaries based on relevance, importance, and recency.

        Args:
            summaries: Summaries to score
            query: Query for relevance scoring

        Returns:
            List of (summary, score) tuples
        """
        scored_summaries = []
        query_lower = query.lower()
        query_words = set(query_lower.split())

        for summary in summaries:
            # Recency score
            recency_score = self._calculate_recency_score(summary.created_at)

            # Relevance score (summary text)
            text_relevance = self._calculate_text_relevance(
                summary.summary_text.lower(),
                query_lower,
                query_words
            )

            # Topic relevance score
            topic_relevance = self._calculate_topic_relevance(
                summary.key_topics,
                query_words
            )

            # Importance score (already 0-1)
            importance_score = summary.importance_score

            # Combined relevance
            relevance_score = max(text_relevance, topic_relevance)

            # Combined score
            combined_score = (
                self.recency_weight * recency_score +
                self.importance_weight * importance_score +
                self.relevance_weight * relevance_score
            )

            scored_summaries.append((summary, combined_score))

        return scored_summaries

    def _calculate_recency_score(self, timestamp: float) -> float:
        """
        Calculate recency score using exponential decay.

        Args:
            timestamp: Event/summary timestamp

        Returns:
            Recency score (0.0-1.0)
        """
        age_hours = (time.time() - timestamp) / 3600
        decay_factor = math.exp(-age_hours / self.recency_half_life_hours * math.log(2))
        return min(1.0, decay_factor)

    def _calculate_text_relevance(
        self,
        text: str,
        query: str,
        query_words: Set[str]
    ) -> float:
        """
        Calculate text relevance score using simple keyword matching.

        Args:
            text: Text to score
            query: Original query
            query_words: Set of query words

        Returns:
            Relevance score (0.0-1.0)
        """
        if not text or not query_words:
            return 0.0

        text_words = set(text.split())

        # Exact phrase match bonus
        if query in text:
            phrase_bonus = 0.5
        else:
            phrase_bonus = 0.0

        # Word overlap score
        overlap_count = len(query_words.intersection(text_words))
        if len(query_words) > 0:
            overlap_score = overlap_count / len(query_words)
        else:
            overlap_score = 0.0

        # Combine scores
        relevance_score = min(1.0, overlap_score + phrase_bonus)

        return relevance_score

    def _calculate_topic_relevance(
        self,
        topics: List[str],
        query_words: Set[str]
    ) -> float:
        """
        Calculate relevance based on topic matching.

        Args:
            topics: List of topics
            query_words: Set of query words

        Returns:
            Topic relevance score (0.0-1.0)
        """
        if not topics or not query_words:
            return 0.0

        topic_words = set()
        for topic in topics:
            topic_words.update(topic.lower().split())

        if len(query_words) > 0:
            overlap_count = len(query_words.intersection(topic_words))
            return overlap_count / len(query_words)

        return 0.0

    def _get_event_type_importance(self, event_type: EventType) -> float:
        """
        Get importance score for different event types.

        Args:
            event_type: Type of event

        Returns:
            Importance score (0.0-1.0)
        """
        importance_map = {
            EventType.USER_INPUT: 0.9,
            EventType.LLM_RESPONSE: 0.8,
            EventType.ERROR_OCCURRED: 0.7,
            EventType.CONTEXT_RETRIEVAL: 0.3,
            EventType.WAKE_DETECTED: 0.2,
            EventType.STT_TRANSCRIPTION: 0.4,
            EventType.TTS_OUTPUT: 0.3,
            EventType.CONVERSATION_START: 0.5,
            EventType.CONVERSATION_END: 0.5,
            EventType.EPISODE_CREATED: 0.1,
            EventType.EPISODE_CONDENSED: 0.1,
            EventType.MEMORY_HOUSEKEEPING: 0.1,
        }

        return importance_map.get(event_type, 0.5)

    def _calculate_total_tokens(
        self,
        events: List[Event],
        summaries: List[EpisodeSummary]
    ) -> int:
        """
        Calculate total token count for retrieved content.

        Args:
            events: Retrieved events
            summaries: Retrieved summaries

        Returns:
            Total estimated token count
        """
        total_tokens = 0

        # Count event tokens
        for event in events:
            if event.token_count:
                total_tokens += event.token_count
            else:
                # Estimate tokens from content
                total_tokens += len(event.content.split()) + 2

        # Count summary tokens
        for summary in summaries:
            # Estimate tokens from summary text
            total_tokens += len(summary.summary_text.split()) + 2

        return total_tokens

    def get_recent_context(
        self,
        hours: float = 1.0,
        max_events: int = 20,
        max_summaries: int = 5
    ) -> ContextRetrievalResult:
        """
        Get recent context without specific query.

        Args:
            hours: Number of hours to look back
            max_events: Maximum events to retrieve
            max_summaries: Maximum summaries to retrieve

        Returns:
            Recent context
        """
        request = ContextRetrievalRequest(
            query="recent conversation context",
            max_events=max_events,
            max_summaries=max_summaries,
            time_window_hours=hours
        )

        return self.retrieve_context(request)

    def get_conversation_context(
        self,
        conversation_id: str,
        max_events: int = 30,
        max_summaries: int = 3
    ) -> ContextRetrievalResult:
        """
        Get context for a specific conversation.

        Args:
            conversation_id: ID of conversation
            max_events: Maximum events to retrieve
            max_summaries: Maximum summaries to retrieve

        Returns:
            Conversation context
        """
        request = ContextRetrievalRequest(
            query="conversation context",
            max_events=max_events,
            max_summaries=max_summaries,
            conversation_id=conversation_id
        )

        return self.retrieve_context(request)

    def search_memory(
        self,
        query: str,
        max_events: int = 15,
        max_summaries: int = 8,
        time_window_hours: Optional[float] = None
    ) -> ContextRetrievalResult:
        """
        Search memory for specific content.

        Args:
            query: Search query
            max_events: Maximum events to retrieve
            max_summaries: Maximum summaries to retrieve
            time_window_hours: Optional time window

        Returns:
            Search results
        """
        request = ContextRetrievalRequest(
            query=query,
            max_events=max_events,
            max_summaries=max_summaries,
            time_window_hours=time_window_hours,
            min_importance=0.3  # Higher threshold for search
        )

        return self.retrieve_context(request)

    def get_retrieval_stats(self) -> Dict[str, Any]:
        """
        Get statistics about context retrieval.

        Returns:
            Dictionary with retrieval statistics
        """
        stats = {}

        # Get base storage stats
        storage_stats = self.store.get_stats()
        stats.update(storage_stats)

        # Add retrieval-specific stats
        conn = self.store._get_connection()

        # Most retrieved event types
        cursor = conn.execute("""
            SELECT event_type, COUNT(*) as count
            FROM events
            WHERE event_type = 'context_retrieval'
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 5
        """)

        retrieval_counts = {}
        for row in cursor.fetchall():
            retrieval_counts[row[0]] = row[1]

        stats["retrieval_counts"] = retrieval_counts

        return stats