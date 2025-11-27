"""
Episode condensation service for memory system.

Provides LLM-based episode summarization and condensation operations
for long-term memory storage and efficient retrieval.

This service wraps the EpisodeCondenser, centralizing episode condensation
logic and exposing it through the UMN bus for agentic housekeeping.
"""

import logging
import time
from typing import Any, Dict, Optional

from src.orchestration.core.umn_bus import UMNSub, UMNPub

logger = logging.getLogger(__name__)

try:
    from src.cognition.mind.memory.condenser import EpisodeCondenser
    from src.cognition.mind.memory.logger import MemoryLogger
    from src.cognition.mind.memory.models import EventType
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False
    EpisodeCondenser = None
    MemoryLogger = None
    EventType = None


class EpisodeCondensationService:
    """
    Episode condensation service for episodic memory system.

    Provides:
    - LLM-based episode summarization
    - Pending episode condensation with configurable limits
    - Episode detection and automatic grouping
    - Condensation statistics and monitoring

    Can operate as UMN subscriber for agentic housekeeping architecture.
    """

    def __init__(self, memory_logger: Optional['MemoryLogger'] = None):
        """
        Initialize episode condensation service.

        Args:
            memory_logger: Optional MemoryLogger for event tracking
        """
        self.memory_logger = memory_logger
        self._condenser: Optional['EpisodeCondenser'] = None

        self._umn_sub: Optional[UMNSub] = None
        self._umn_pub: Optional[UMNPub] = None

    @property
    def condenser(self) -> 'EpisodeCondenser':
        """Lazy-load episode condenser."""
        if self._condenser is None and HAS_MEMORY:
            self._condenser = EpisodeCondenser()
        return self._condenser

    def subscribe_to_umn(self) -> None:
        """Subscribe to UMN for agentic housekeeping."""
        self._umn_pub = UMNPub()
        self._umn_sub = UMNSub(
            topic="Q_HOUSEKEEPING.CONDENSE",
            on_json=self._handle_condensation_request,
            zooid_name="episode_condensation_service",
            niche="memory"
        )
        logger.info("[episode_condensation] Subscribed to Q_HOUSEKEEPING.CONDENSE")

    def _handle_condensation_request(self, msg: dict) -> None:
        """Handle UMN request for episode condensation."""
        request_id = msg.get('request_id', 'unknown')
        facts = msg.get('facts', {})
        max_episodes = facts.get('max_episodes')

        try:
            results = self.condense_pending_episodes(max_episodes=max_episodes)

            self._umn_pub.emit(
                signal="Q_HOUSEKEEPING.CONDENSE.COMPLETE",
                ecosystem="memory",
                facts={
                    'request_id': request_id,
                    'success': True,
                    'results': results
                }
            )

        except Exception as e:
            logger.error(f"[episode_condensation] Error during condensation: {e}", exc_info=True)
            if self._umn_pub:
                self._umn_pub.emit(
                    signal="Q_HOUSEKEEPING.CONDENSE.COMPLETE",
                    ecosystem="memory",
                    facts={
                        'request_id': request_id,
                        'success': False,
                        'error': str(e)
                    }
                )

    def condense_pending_episodes(self, max_episodes: Optional[int] = None) -> Dict[str, Any]:
        """
        Condense pending uncondensed episodes.

        Processes up to max_episodes uncondensed episodes, generating LLM-based
        summaries for each. Returns comprehensive results including counts,
        statistics, and any errors encountered.

        Args:
            max_episodes: Maximum number of episodes to condense (None for all pending)

        Returns:
            Dictionary with condensation results:
            - processed: int, number of episodes successfully condensed
            - episodes_condensed: int, count of episodes that received summaries
            - episodes_skipped: int, count of episodes that couldn't be condensed
            - total_time_seconds: float, time spent on condensation
            - avg_importance_score: float, average importance of generated summaries
            - top_topics: dict, most frequent topics in condensed episodes
            - errors: list, any errors encountered
        """
        if not HAS_MEMORY or self.condenser is None:
            logger.warning("[episode_condensation] Memory system not available")
            return {
                "processed": 0,
                "episodes_condensed": 0,
                "episodes_skipped": 0,
                "total_time_seconds": 0,
                "errors": ["Memory system not available"]
            }

        results = {
            "processed": 0,
            "episodes_condensed": 0,
            "episodes_skipped": 0,
            "total_time_seconds": 0,
            "avg_importance_score": 0.0,
            "top_topics": {},
            "errors": []
        }

        start_time = time.time()

        try:
            if max_episodes is None:
                max_episodes = 10

            processed = self.condenser.process_uncondensed_episodes(limit=max_episodes)
            results["processed"] = processed
            results["episodes_condensed"] = processed

            if processed > 0:
                logger.info(f"[episode_condensation] Condensed {processed} episodes")

                if self.memory_logger and HAS_MEMORY:
                    self.memory_logger.log_event(
                        event_type=EventType.MEMORY_HOUSEKEEPING,
                        content=f"Condensed {processed} episodes",
                        metadata={"episodes_condensed": processed}
                    )

            stats = self.condenser.get_condensation_stats()
            results["avg_importance_score"] = stats.get("avg_importance_score", 0.0)
            results["top_topics"] = stats.get("top_topics", {})

        except Exception as e:
            logger.error(f"[episode_condensation] Error condensing episodes: {e}", exc_info=True)
            results["errors"].append(str(e))
            results["episodes_skipped"] = max_episodes - results["processed"]

        finally:
            results["total_time_seconds"] = time.time() - start_time

        return results

    def get_condensation_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the condensation process.

        Returns:
            Dictionary with condensation statistics including episode counts,
            importance scores, and topic distribution
        """
        if not HAS_MEMORY or self.condenser is None:
            logger.warning("[episode_condensation] Memory system not available")
            return {}

        try:
            return self.condenser.get_condensation_stats()
        except Exception as e:
            logger.error(f"[episode_condensation] Error getting stats: {e}", exc_info=True)
            return {"error": str(e)}

    def shutdown(self) -> None:
        """Close UMN subscriptions."""
        if self._umn_sub:
            self._umn_sub.close()
            logger.info("[episode_condensation] Closed UMN subscription")
