"""
Enhanced event logging system for KLoROS episodic memory.

Provides structured logging of all voice interaction events with automatic
conversation grouping, metadata enrichment, and integration with the storage layer.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from .models import Event, EventType
from .storage import MemoryStore

# Optional dependencies - these may fail if dependencies are missing
try:
    from .embeddings import get_embedding_engine
except ImportError:
    get_embedding_engine = lambda: None

try:
    from .vector_store import get_vector_store
except ImportError:
    get_vector_store = lambda: None

try:
    from .graph import MemoryGraph
except ImportError:
    MemoryGraph = None

try:
    from .sentiment import get_sentiment_analyzer
except ImportError:
    get_sentiment_analyzer = lambda: None


class MemoryLogger:
    """
    Enhanced event logger for KLoROS memory system.

    Features:
    - Automatic conversation grouping
    - Rich metadata collection
    - Integration with storage layer
    - Performance optimizations
    """

    def __init__(self, store: Optional[MemoryStore] = None, enable_embeddings: bool = True, enable_graph: bool = True, enable_sentiment: bool = True):
        """
        Initialize the memory logger.

        Args:
            store: Memory storage instance (creates default if None)
            enable_embeddings: Whether to generate semantic embeddings (default: True)
            enable_graph: Whether to create graph edges (default: True)
            enable_sentiment: Whether to analyze sentiment (default: True)
        """
        self.store = store or MemoryStore()
        self._current_conversation_id: Optional[str] = None
        self._conversation_start_time: Optional[float] = None
        self._event_cache: List[Event] = []
        # Strip inline comments from env vars before parsing
        cache_size_val = os.getenv("KLR_MEMORY_CACHE_SIZE", "50").split("#")[0].strip()
        self._cache_size = int(cache_size_val)
        self._last_event_id: Optional[int] = None  # Track last event for temporal edges

        # Phase 1: Semantic embeddings
        embeddings_val = os.getenv("KLR_ENABLE_EMBEDDINGS", "1").split("#")[0].strip()
        self.enable_embeddings = enable_embeddings and int(embeddings_val)
        if self.enable_embeddings:
            try:
                self.embedding_engine = get_embedding_engine()
                self.vector_store = get_vector_store()
            except Exception as e:
                logging.warning(f"[memory] Failed to initialize embeddings: {e}")
                self.enable_embeddings = False

        # Phase 3: Memory graph
        graph_val = os.getenv("KLR_ENABLE_GRAPH", "1").split("#")[0].strip()
        self.enable_graph = enable_graph and int(graph_val) and MemoryGraph is not None
        if self.enable_graph:
            try:
                self.graph = MemoryGraph(store=self.store)
            except Exception as e:
                logging.warning(f"[memory] Failed to initialize graph: {e}")
                self.enable_graph = False

        # Phase 4: Sentiment analysis
        sentiment_val = os.getenv("KLR_ENABLE_SENTIMENT", "1").split("#")[0].strip()
        self.enable_sentiment = enable_sentiment and int(sentiment_val)
        if self.enable_sentiment:
            try:
                self.sentiment_analyzer = get_sentiment_analyzer()
            except Exception as e:
                logging.warning(f"[memory] Failed to initialize sentiment analyzer: {e}")
                self.enable_sentiment = False

    def start_conversation(self, conversation_id: Optional[str] = None) -> str:
        """
        Start a new conversation session.

        Args:
            conversation_id: Optional conversation ID (generates UUID if None)

        Returns:
            The conversation ID
        """
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        self._current_conversation_id = conversation_id
        self._conversation_start_time = time.time()

        # Log conversation start event
        self.log_event(
            event_type=EventType.CONVERSATION_START,
            content=f"Started conversation {conversation_id}",
            metadata={"conversation_id": conversation_id}
        )

        return conversation_id

    def end_conversation(self) -> Optional[str]:
        """
        End the current conversation session.

        Returns:
            The ended conversation ID, or None if no active conversation
        """
        if self._current_conversation_id is None:
            return None

        conversation_id = self._current_conversation_id
        duration = time.time() - (self._conversation_start_time or time.time())

        # Log conversation end event
        self.log_event(
            event_type=EventType.CONVERSATION_END,
            content=f"Ended conversation {conversation_id}",
            metadata={
                "conversation_id": conversation_id,
                "duration_seconds": duration
            }
        )

        # Flush any cached events
        self._flush_cache()

        self._current_conversation_id = None
        self._conversation_start_time = None

        return conversation_id

    def log_event(
        self,
        event_type: EventType,
        content: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
        token_count: Optional[int] = None,
        conversation_id: Optional[str] = None
    ) -> Event:
        """
        Log a single event to memory.

        Args:
            event_type: Type of event
            content: Main content of the event
            metadata: Additional metadata
            confidence: Confidence score (0.0-1.0)
            token_count: Token count for LLM events
            conversation_id: Override conversation ID

        Returns:
            The created event
        """
        # Use current conversation ID if not specified
        if conversation_id is None:
            conversation_id = self._current_conversation_id

        # Enrich metadata with system information
        enriched_metadata = metadata.copy() if metadata else {}
        enriched_metadata.update({
            "logger_version": "1.0.0",
            "system_timestamp": time.time(),
            "process_id": os.getpid(),
        })

        # Create the event
        event = Event(
            timestamp=time.time(),
            event_type=event_type,
            content=content,
            metadata=enriched_metadata,
            conversation_id=conversation_id,
            confidence=confidence,
            token_count=token_count
        )

        # Add to cache or store immediately
        if len(self._event_cache) < self._cache_size:
            self._event_cache.append(event)
        else:
            # Cache full, flush and add new event
            self._flush_cache()
            self._event_cache.append(event)

        return event

    def log_wake_detection(
        self,
        transcript: str,
        confidence: float,
        wake_phrase: str,
        audio_energy: Optional[float] = None
    ) -> Event:
        """
        Log a wake word detection event.

        Args:
            transcript: The transcribed text that triggered wake
            confidence: Confidence score of the detection
            wake_phrase: The matched wake phrase
            audio_energy: Optional audio energy level

        Returns:
            The logged event
        """
        metadata = {
            "wake_phrase": wake_phrase,
            "transcript": transcript,
            "audio_energy": audio_energy,
            "detection_method": "fuzzy_phonetic"
        }

        return self.log_event(
            event_type=EventType.WAKE_DETECTED,
            content=f"Wake detected: '{transcript}' -> '{wake_phrase}'",
            metadata=metadata,
            confidence=confidence
        )

    def log_user_input(
        self,
        transcript: str,
        confidence: float,
        audio_duration: Optional[float] = None,
        vad_confidence: Optional[float] = None
    ) -> Event:
        """
        Log a user speech input event.

        Args:
            transcript: Transcribed user speech
            confidence: STT confidence score
            audio_duration: Duration of audio in seconds
            vad_confidence: Voice activity detection confidence

        Returns:
            The logged event
        """
        metadata = {
            "stt_engine": "vosk",
            "audio_duration": audio_duration,
            "vad_confidence": vad_confidence,
            "transcript_length": len(transcript)
        }

        # Estimate token count (rough approximation)
        token_count = max(1, len(transcript.split()) + 2)

        return self.log_event(
            event_type=EventType.USER_INPUT,
            content=transcript,
            metadata=metadata,
            confidence=confidence,
            token_count=token_count
        )

    def log_llm_response(
        self,
        response: str,
        model: str = "qwen2.5:14b-instruct-q4_0",
        prompt_tokens: Optional[int] = None,
        response_tokens: Optional[int] = None,
        generation_time: Optional[float] = None,
        temperature: Optional[float] = None
    ) -> Event:
        """
        Log an LLM response event.

        Args:
            response: The generated response text
            model: Model used for generation
            prompt_tokens: Number of prompt tokens
            response_tokens: Number of response tokens
            generation_time: Time taken to generate response
            temperature: Generation temperature

        Returns:
            The logged event
        """
        metadata = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "response_tokens": response_tokens,
            "generation_time": generation_time,
            "temperature": temperature,
            "response_length": len(response)
        }

        total_tokens = 0
        if prompt_tokens:
            total_tokens += prompt_tokens
        if response_tokens:
            total_tokens += response_tokens

        return self.log_event(
            event_type=EventType.LLM_RESPONSE,
            content=response,
            metadata=metadata,
            token_count=total_tokens or None
        )

    def log_tts_output(
        self,
        text: str,
        voice_model: str = "piper",
        audio_duration: Optional[float] = None,
        synthesis_time: Optional[float] = None
    ) -> Event:
        """
        Log a TTS synthesis event.

        Args:
            text: Text that was synthesized
            voice_model: TTS model/voice used
            audio_duration: Duration of synthesized audio
            synthesis_time: Time taken to synthesize

        Returns:
            The logged event
        """
        metadata = {
            "tts_engine": voice_model,
            "audio_duration": audio_duration,
            "synthesis_time": synthesis_time,
            "text_length": len(text),
            "word_count": len(text.split())
        }

        return self.log_event(
            event_type=EventType.TTS_OUTPUT,
            content=text,
            metadata=metadata
        )

    def log_error(
        self,
        error_message: str,
        error_type: str,
        component: str,
        stack_trace: Optional[str] = None
    ) -> Event:
        """
        Log an error event.

        Args:
            error_message: Description of the error
            error_type: Type/class of error
            component: Component where error occurred
            stack_trace: Optional stack trace

        Returns:
            The logged event
        """
        metadata = {
            "error_type": error_type,
            "component": component,
            "stack_trace": stack_trace,
            "error_hash": hashlib.md5(error_message.encode()).hexdigest()[:8]
        }

        return self.log_event(
            event_type=EventType.ERROR_OCCURRED,
            content=error_message,
            metadata=metadata
        )

    def log_context_retrieval(
        self,
        query: str,
        retrieved_events: int,
        retrieved_summaries: int,
        total_tokens: int,
        retrieval_time: float
    ) -> Event:
        """
        Log a context retrieval event.

        Args:
            query: Query used for retrieval
            retrieved_events: Number of events retrieved
            retrieved_summaries: Number of summaries retrieved
            total_tokens: Total tokens in retrieved content
            retrieval_time: Time taken for retrieval

        Returns:
            The logged event
        """
        metadata = {
            "query_hash": hashlib.md5(query.encode()).hexdigest()[:8],
            "retrieved_events": retrieved_events,
            "retrieved_summaries": retrieved_summaries,
            "total_tokens": total_tokens,
            "retrieval_time": retrieval_time
        }

        return self.log_event(
            event_type=EventType.CONTEXT_RETRIEVAL,
            content=f"Retrieved {retrieved_events} events, {retrieved_summaries} summaries",
            metadata=metadata,
            token_count=total_tokens
        )

    def log_affective_event(
        self,
        event_type: str,
        affect: Dict[str, float],
        emotions: Dict[str, float],
        homeostatic_state: Dict[str, Dict[str, float]],
        description: str,
        event_metadata: Optional[Dict[str, Any]] = None
    ) -> Event:
        """
        Log an affective event (consciousness substrate activity).

        Args:
            event_type: Type of event that triggered affect (e.g., "user_input", "error_detected")
            affect: Current affect state (valence, arousal, dominance)
            emotions: Current intensities of 7 primary emotions
            homeostatic_state: Current state of homeostatic variables
            description: Natural language description of affective response
            event_metadata: Additional metadata from the triggering event

        Returns:
            The logged event
        """
        metadata = {
            "affective_event_type": event_type,
            "affect": affect,
            "emotions": emotions,
            "homeostatic_state": homeostatic_state,
            "dominant_emotion": max(emotions.items(), key=lambda x: x[1])[0] if emotions else None,
            "dominant_emotion_intensity": max(emotions.values()) if emotions else 0.0,
            "wellbeing_valence": affect.get("valence", 0.0),
        }

        # Include any additional metadata from the triggering event
        if event_metadata:
            metadata["trigger_metadata"] = event_metadata

        return self.log_event(
            event_type=EventType.AFFECTIVE_EVENT,
            content=description,
            metadata=metadata
        )

    def _flush_cache(self) -> None:
        """Flush cached events to storage."""
        if not self._event_cache:
            return

        # Phase 4: Analyze sentiment before storing
        if self.enable_sentiment:
            try:
                for event in self._event_cache:
                    if event.content.strip():
                        sentiment_result = self.sentiment_analyzer.analyze(event.content)
                        # Store sentiment in metadata
                        event.metadata["sentiment_score"] = sentiment_result["sentiment_score"]
                        event.metadata["emotion_type"] = sentiment_result["emotion_type"]
                        event.metadata["emotional_intensity"] = sentiment_result["intensity"]
            except Exception as e:
                logging.error(f"[memory] Failed to analyze sentiment: {e}")

        # Store all cached events to SQLite
        for event in self._event_cache:
            event.id = self.store.store_event(event)

        # Phase 4: Update sentiment columns in database
        if self.enable_sentiment:
            try:
                conn = self.store._get_connection()
                for event in self._event_cache:
                    if event.id and "sentiment_score" in event.metadata:
                        conn.execute(
                            "UPDATE events SET sentiment_score = ?, emotion_type = ? WHERE id = ?",
                            (
                                event.metadata.get("sentiment_score"),
                                event.metadata.get("emotion_type"),
                                event.id
                            )
                        )
            except Exception as e:
                logging.error(f"[memory] Failed to update sentiment in database: {e}")

        # Phase 1: Generate embeddings and store in vector store
        if self.enable_embeddings:
            try:
                # Batch embed all events with content
                events_to_embed = [e for e in self._event_cache if e.content.strip()]
                if events_to_embed:
                    texts = [e.content for e in events_to_embed]
                    embeddings = self.embedding_engine.embed_batch(texts, show_progress=False)

                    # Store in vector store with metadata
                    for event, embedding in zip(events_to_embed, embeddings):
                        metadata = {
                            "event_type": event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
                            "conversation_id": event.conversation_id if event.conversation_id else "",
                            "timestamp": float(event.timestamp)
                        }
                        self.vector_store.add(
                            text=event.content,
                            doc_id=f"event_{event.id}",
                            metadata=metadata,
                            embedding=embedding
                        )
            except Exception as e:
                logging.error(f"[memory] Failed to generate embeddings during flush: {e}")

        # Phase 3: Create graph edges
        if self.enable_graph and len(self._event_cache) > 0:
            try:
                # Create temporal edges between consecutive events
                for i in range(len(self._event_cache) - 1):
                    if self._event_cache[i].id and self._event_cache[i + 1].id:
                        self.graph.add_temporal_edge(
                            event1_id=self._event_cache[i].id,
                            event2_id=self._event_cache[i + 1].id,
                            weight=0.8
                        )

                # Link first event to last event in previous cache (temporal continuity)
                if self._last_event_id and self._event_cache[0].id:
                    self.graph.add_temporal_edge(
                        event1_id=self._last_event_id,
                        event2_id=self._event_cache[0].id,
                        weight=0.7
                    )

                # Create conversational edges if in a conversation
                if self._current_conversation_id:
                    event_ids = [e.id for e in self._event_cache if e.id and e.conversation_id == self._current_conversation_id]
                    if len(event_ids) > 1:
                        self.graph.add_conversational_edges(
                            event_ids=event_ids,
                            conversation_id=self._current_conversation_id
                        )

                # Update last event ID for next flush
                if self._event_cache[-1].id:
                    self._last_event_id = self._event_cache[-1].id

            except Exception as e:
                logging.error(f"[memory] Failed to create graph edges during flush: {e}")

        self._event_cache.clear()

    def get_conversation_events(
        self,
        conversation_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Event]:
        """
        Get events for a specific conversation.

        Args:
            conversation_id: Conversation ID (uses current if None)
            limit: Maximum number of events to return

        Returns:
            List of events for the conversation
        """
        if conversation_id is None:
            conversation_id = self._current_conversation_id

        if conversation_id is None:
            return []

        return self.store.get_events(
            conversation_id=conversation_id,
            limit=limit
        )

    def get_recent_events(
        self,
        hours: float = 24.0,
        limit: int = 100
    ) -> List[Event]:
        """
        Get recent events within a time window.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of events to return

        Returns:
            List of recent events
        """
        start_time = time.time() - (hours * 3600)

        return self.store.get_events(
            start_time=start_time,
            limit=limit
        )

    def close(self) -> None:
        """Close the logger and flush any remaining events."""
        self._flush_cache()
        self.store.close()