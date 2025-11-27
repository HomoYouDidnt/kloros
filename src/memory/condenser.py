"""
Episode grouping and Ollama-based condensation engine for KLoROS memory.

Groups related events into episodes and uses local Ollama LLM to generate
concise summaries for long-term memory storage and efficient retrieval.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from .models import Event, Episode, EpisodeSummary, EventType
from .storage import MemoryStore

try:
    from config.models_config import get_ollama_context_size
except ImportError:
    def get_ollama_context_size(check_vram: bool = False):
        return 2048


class EpisodeCondenser:
    """
    Episode grouping and LLM-based condensation engine.

    Features:
    - Automatic episode detection and grouping
    - Token budget management
    - LLM-powered summarization using local Ollama
    - Importance scoring for memory retention
    """

    def __init__(
        self,
        store: Optional[MemoryStore] = None,
        ollama_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        Initialize the episode condenser.

        Args:
            store: Memory storage instance
            ollama_url: Ollama API endpoint (defaults to SSOT config)
            model: LLM model to use for condensation (defaults to SSOT config)
        """
        # Get defaults from SSOT config
        if ollama_url is None:
            try:
                from config.models_config import get_ollama_url
                ollama_url = get_ollama_url() + "/api/generate"
            except ImportError:
                ollama_url = "http://localhost:11434/api/generate"
        if model is None:
            try:
                from config.models_config import get_ollama_model
                model = get_ollama_model()
            except ImportError:
                model = "meta-llama/Llama-3.1-8B-Instruct"

        self.store = store or MemoryStore()
        self.ollama_url = ollama_url
        self.model = model

        # Configuration from environment
        self.episode_timeout = float(os.getenv("KLR_EPISODE_TIMEOUT", "300"))  # 5 minutes
        self.min_events_per_episode = int(os.getenv("KLR_MIN_EPISODE_EVENTS", "3"))
        self.max_episode_tokens = int(os.getenv("KLR_MAX_EPISODE_TOKENS", "2000"))
        self.condensation_token_budget = int(os.getenv("KLR_CONDENSATION_BUDGET", "800"))

    def group_events_into_episodes(
        self,
        conversation_id: str,
        min_events: Optional[int] = None
    ) -> List[Episode]:
        """
        Group events from a conversation into coherent episodes.

        Args:
            conversation_id: ID of conversation to process
            min_events: Minimum events per episode (uses default if None)

        Returns:
            List of created episodes
        """
        if min_events is None:
            min_events = self.min_events_per_episode

        # Get all events for this conversation
        events = self.store.get_events(
            conversation_id=conversation_id,
            limit=1000  # Large limit to get all events
        )

        if len(events) < min_events:
            return []

        # Sort events by timestamp
        events.sort(key=lambda e: e.timestamp)

        episodes = []
        current_episode_events = []
        episode_start_time = None

        for event in events:
            # Start new episode if this is the first event
            if not current_episode_events:
                current_episode_events = [event]
                episode_start_time = event.timestamp
                continue

            # Check if this event should be in the same episode
            time_gap = event.timestamp - current_episode_events[-1].timestamp

            # End current episode if:
            # 1. Time gap is too large
            # 2. Too many tokens accumulated
            # 3. Conversation end event
            should_end_episode = (
                time_gap > self.episode_timeout or
                self._calculate_episode_tokens(current_episode_events) > self.max_episode_tokens or
                event.event_type == EventType.CONVERSATION_END
            )

            if should_end_episode and len(current_episode_events) >= min_events:
                # Create episode from current events
                episode = self._create_episode_from_events(
                    current_episode_events,
                    conversation_id
                )
                if episode:
                    episodes.append(episode)

                # Start new episode
                current_episode_events = [event]
                episode_start_time = event.timestamp
            else:
                # Add to current episode
                current_episode_events.append(event)

        # Handle final episode
        if len(current_episode_events) >= min_events:
            episode = self._create_episode_from_events(
                current_episode_events,
                conversation_id
            )
            if episode:
                episodes.append(episode)

        return episodes

    def _create_episode_from_events(
        self,
        events: List[Event],
        conversation_id: str
    ) -> Optional[Episode]:
        """
        Create an Episode object from a list of events.

        Args:
            events: List of events to group
            conversation_id: Conversation ID

        Returns:
            Created Episode or None if invalid
        """
        if not events:
            return None

        events.sort(key=lambda e: e.timestamp)

        episode = Episode(
            start_time=events[0].timestamp,
            end_time=events[-1].timestamp,
            conversation_id=conversation_id,
            event_count=len(events),
            token_count=self._calculate_episode_tokens(events)
        )

        # Store in database
        episode.id = self.store.store_episode(episode)
        return episode

    def _calculate_episode_tokens(self, events: List[Event]) -> int:
        """
        Calculate total token count for a list of events.

        Args:
            events: List of events

        Returns:
            Total token count
        """
        total_tokens = 0
        for event in events:
            if event.token_count:
                total_tokens += event.token_count
            else:
                # Estimate tokens from content length
                content_tokens = max(1, len(event.content.split()) + 1)
                total_tokens += content_tokens

        return total_tokens

    def condense_episode(self, episode: Episode) -> Optional[EpisodeSummary]:
        """
        Generate an LLM summary for an episode.

        Args:
            episode: Episode to condense

        Returns:
            Generated summary or None if failed
        """
        if episode.is_condensed:
            # Already condensed, return existing summary
            summaries = self.store.get_summaries(episode_id=episode.id, limit=1)
            return summaries[0] if summaries else None

        # Get events for this episode
        events = self.store.get_events(
            conversation_id=episode.conversation_id,
            start_time=episode.start_time,
            end_time=episode.end_time,
            limit=1000
        )

        if not events:
            return None

        # Generate summary using LLM
        summary_data = self._generate_summary_with_llm(events, episode)
        if not summary_data:
            return None

        # Create EpisodeSummary object
        summary = EpisodeSummary(
            episode_id=episode.id,
            summary_text=summary_data["summary"],
            key_topics=summary_data.get("topics", []),
            emotional_tone=summary_data.get("tone"),
            importance_score=summary_data.get("importance", 0.5),
            model_used=self.model,
            token_budget_used=summary_data.get("tokens_used", 0)
        )

        # Store summary
        summary.id = self.store.store_summary(summary)

        # Mark episode as condensed
        self.store.mark_episode_condensed(episode.id)

        return summary

    def _generate_summary_with_llm(
        self,
        events: List[Event],
        episode: Episode
    ) -> Optional[Dict[str, Any]]:
        """
        Use Ollama LLM to generate episode summary.

        Args:
            events: Events to summarize
            episode: Episode metadata

        Returns:
            Dictionary with summary data or None if failed
        """
        # Import KLoROS persona
        try:
            from src.persona.kloros import PERSONA_PROMPT
            system_prompt = PERSONA_PROMPT.strip()
        except ImportError:
            system_prompt = "You are KLoROS, a precise, calm assistant with clinical wit."

        # Build context from events
        context_parts = []
        total_content_tokens = 0

        for event in sorted(events, key=lambda e: e.timestamp):
            if total_content_tokens > self.condensation_token_budget:
                break

            event_text = f"[{event.event_type if isinstance(event.event_type, str) else event.event_type.value}] {event.content}"
            if event.metadata:
                # Add key metadata
                if event.confidence is not None:
                    event_text += f" (confidence: {event.confidence:.2f})"

            context_parts.append(event_text)
            total_content_tokens += len(event_text.split()) + 2

        context_text = "\\n".join(context_parts)

        # Create summarization prompt
        prompt = f"""Please analyze this conversation episode and provide a structured summary.

Episode Context:
{context_text}

Please provide a JSON response with the following structure:
{{
    "summary": "A concise 2-3 sentence summary of the key points and outcomes",
    "topics": ["topic1", "topic2", "topic3"],
    "tone": "conversational|technical|helpful|problem_solving|other",
    "importance": 0.7
}}

The importance score should be 0.0-1.0 where:
- 0.0-0.3: Routine interactions, greetings, simple questions
- 0.4-0.6: Standard conversations, explanations, basic help
- 0.7-0.8: Important decisions, complex problems, significant learning
- 0.9-1.0: Critical issues, major discoveries, exceptional interactions

Focus on capturing the essence and outcomes rather than specific details."""

        # Call Ollama API
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
                "options": {
                    "num_gpu": 999,
                    "main_gpu": 0,
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "num_ctx": get_ollama_context_size(check_vram=False)
                }
            }

            response = requests.post(self.ollama_url, json=payload, timeout=60)

            if response.status_code != 200:
                return None

            response_data = response.json()
            response_text = response_data.get("response", "").strip()

            if not response_text:
                return None

            # Try to parse JSON response
            try:
                # Look for JSON in the response
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1

                if json_start >= 0 and json_end > json_start:
                    json_text = response_text[json_start:json_end]
                    summary_data = json.loads(json_text)
                else:
                    # Fallback: treat entire response as summary
                    summary_data = {
                        "summary": response_text,
                        "topics": [],
                        "tone": "conversational",
                        "importance": 0.5
                    }

                # Validate and clean data
                summary_data["summary"] = str(summary_data.get("summary", "")).strip()
                summary_data["topics"] = [
                    str(t).strip() for t in summary_data.get("topics", [])
                    if str(t).strip()
                ][:5]  # Limit to 5 topics
                summary_data["tone"] = str(summary_data.get("tone", "conversational")).strip()

                importance = summary_data.get("importance", 0.5)
                if isinstance(importance, (int, float)):
                    summary_data["importance"] = max(0.0, min(1.0, float(importance)))
                else:
                    summary_data["importance"] = 0.5

                # Estimate tokens used
                summary_data["tokens_used"] = len(prompt.split()) + len(response_text.split())

                return summary_data

            except json.JSONDecodeError:
                # Fallback for non-JSON response
                return {
                    "summary": response_text[:500],  # Truncate if too long
                    "topics": [],
                    "tone": "conversational",
                    "importance": 0.5,
                    "tokens_used": len(prompt.split()) + len(response_text.split())
                }

        except requests.RequestException:
            return None

    def process_uncondensed_episodes(self, limit: int = 10) -> int:
        """
        Process uncondensed episodes and generate summaries.

        Args:
            limit: Maximum number of episodes to process

        Returns:
            Number of episodes processed
        """
        # Get uncondensed episodes
        episodes = self.store.get_episodes(is_condensed=False, limit=limit)

        processed = 0
        for episode in episodes:
            summary = self.condense_episode(episode)
            if summary:
                processed += 1

        return processed

    def auto_episode_detection(self) -> int:
        """
        Automatically detect and create episodes from recent events.

        Returns:
            Number of episodes created
        """
        # Get recent conversations that might need episode grouping
        recent_time = time.time() - (24 * 3600)  # Last 24 hours
        recent_events = self.store.get_events(
            start_time=recent_time,
            limit=1000
        )

        # Group by conversation
        conversation_events = {}
        for event in recent_events:
            if event.conversation_id:
                if event.conversation_id not in conversation_events:
                    conversation_events[event.conversation_id] = []
                conversation_events[event.conversation_id].append(event)

        total_episodes = 0
        for conversation_id, events in conversation_events.items():
            episodes = self.group_events_into_episodes(conversation_id)
            total_episodes += len(episodes)

        return total_episodes

    def get_condensation_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the condensation process.

        Returns:
            Dictionary with condensation statistics
        """
        stats = self.store.get_stats()

        # Add condensation-specific stats
        conn = self.store._get_connection()

        # Average importance scores
        cursor = conn.execute("SELECT AVG(importance_score) FROM episode_summaries")
        row = cursor.fetchone()
        stats["avg_importance_score"] = row[0] if row and row[0] else 0.0

        # Top topics
        cursor = conn.execute("""
            SELECT key_topics, COUNT(*) as count
            FROM episode_summaries
            WHERE key_topics != '[]'
            GROUP BY key_topics
            ORDER BY count DESC
            LIMIT 5
        """)

        top_topics = {}
        for row in cursor.fetchall():
            try:
                topics = json.loads(row[0])
                for topic in topics:
                    top_topics[topic] = top_topics.get(topic, 0) + row[1]
            except json.JSONDecodeError:
                continue

        stats["top_topics"] = dict(sorted(top_topics.items(), key=lambda x: x[1], reverse=True)[:10])

        return stats