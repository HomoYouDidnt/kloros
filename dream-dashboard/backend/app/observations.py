"""
Observation Management for D-REAM Dashboard

Aggregates and serves KLoROS autonomous observations from:
- Reflection log (/home/kloros/.kloros/reflection.log)
- Memory database (/home/kloros/.kloros/memory.db)

Provides data for the Observations page showing:
- Recent observations (last 24-48h)
- Historical patterns
- Phase-specific insights (Phases 1-4)
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import Counter


@dataclass
class Observation:
    """Structured observation data."""
    id: str
    timestamp: float
    phase: int
    insight_type: str
    title: str
    content: str
    confidence: float
    keywords: List[str]
    source: str  # 'reflection_log' or 'memory_db'

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            **asdict(self),
            'timestamp_iso': datetime.fromtimestamp(self.timestamp).isoformat(),
            'relative_time': self._format_relative_time(),
            'confidence_level': self._get_confidence_level(),
            'phase_name': self._get_phase_name()
        }

    def _format_relative_time(self) -> str:
        """Format timestamp as relative time (e.g., '2 hours ago')."""
        now = time.time()
        diff = now - self.timestamp

        if diff < 60:
            return "just now"
        elif diff < 3600:
            mins = int(diff / 60)
            return f"{mins} minute{'s' if mins != 1 else ''} ago"
        elif diff < 86400:
            hours = int(diff / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = int(diff / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"

    def _get_confidence_level(self) -> str:
        """Get confidence level label."""
        if self.confidence >= 0.8:
            return "VERY_HIGH"
        elif self.confidence >= 0.7:
            return "HIGH"
        elif self.confidence >= 0.5:
            return "MEDIUM"
        else:
            return "LOW"

    def _get_phase_name(self) -> str:
        """Get human-readable phase name."""
        phase_names = {
            1: "Semantic Analysis",
            2: "Meta-Cognitive",
            3: "Cross-Cycle Synthesis",
            4: "Adaptive Optimization"
        }
        return phase_names.get(self.phase, f"Phase {self.phase}")


class ObservationManager:
    """Manages observation data aggregation and retrieval."""

    def __init__(self):
        self.reflection_log_path = Path("/home/kloros/.kloros/reflection.log")
        self.memory_db_path = Path("/home/kloros/.kloros/memory.db")
        self._last_check_timestamp = 0

    def get_observations(self, hours: int = 48, phase: Optional[int] = None,
                        limit: int = 100) -> Dict[str, Any]:
        """
        Get aggregated observations.

        Args:
            hours: Number of hours to look back for recent observations
            phase: Filter by specific phase (1-4), None for all
            limit: Maximum number of observations to return

        Returns:
            Dictionary with recent observations, historical patterns, and stats
        """
        # Get observations from both sources
        recent_from_db = self._query_memory_db(hours=hours)
        recent_from_log = self._parse_recent_reflection_log(hours=hours)

        # Combine and deduplicate
        all_observations = self._deduplicate(recent_from_db + recent_from_log)

        # Filter by phase if specified
        if phase is not None:
            all_observations = [o for o in all_observations if o.phase == phase]

        # Sort by timestamp (newest first)
        all_observations.sort(key=lambda o: o.timestamp, reverse=True)

        # Limit results
        all_observations = all_observations[:limit]

        return {
            'recent': [o.to_dict() for o in all_observations[:20]],
            'historical_patterns': self._extract_patterns(all_observations),
            'by_phase': self._group_by_phase(all_observations),
            'stats': self._calculate_stats(all_observations)
        }

    def get_new_since(self, timestamp: float) -> List[Observation]:
        """
        Get new observations since a given timestamp.
        Used for real-time SSE updates.

        Args:
            timestamp: Unix timestamp to check from

        Returns:
            List of new observations
        """
        recent = self._query_memory_db(hours=1)  # Check last hour
        new_obs = [o for o in recent if o.timestamp > timestamp]
        return new_obs

    def _query_memory_db(self, hours: int = 24) -> List[Observation]:
        """
        Query memory database for self-reflection events.

        Args:
            hours: Number of hours to look back

        Returns:
            List of Observation objects
        """
        if not self.memory_db_path.exists():
            return []

        observations = []
        cutoff = time.time() - (hours * 3600)

        try:
            conn = sqlite3.connect(str(self.memory_db_path))
            cursor = conn.cursor()

            # Query self-reflection events
            cursor.execute("""
                SELECT timestamp, content, metadata, conversation_id, confidence
                FROM events
                WHERE event_type = 'self_reflection'
                  AND timestamp > ?
                ORDER BY timestamp DESC
            """, (cutoff,))

            for row in cursor.fetchall():
                timestamp, content, metadata_json, conv_id, confidence = row

                try:
                    metadata = json.loads(metadata_json) if metadata_json else {}
                except json.JSONDecodeError:
                    metadata = {}

                # Extract observation fields
                obs = Observation(
                    id=f"mem_{int(timestamp)}_{conv_id or 'none'}",
                    timestamp=timestamp,
                    phase=metadata.get('phase', 1),
                    insight_type=metadata.get('insight_type', 'general'),
                    title=metadata.get('title', content[:100]),
                    content=content,
                    confidence=confidence or 0.5,
                    keywords=metadata.get('keywords', []),
                    source='memory_db'
                )
                observations.append(obs)

            conn.close()

        except sqlite3.Error as e:
            print(f"[observations] Database error: {e}")

        return observations

    def _parse_recent_reflection_log(self, hours: int = 48) -> List[Observation]:
        """
        Parse reflection log for recent observations.

        Args:
            hours: Number of hours to look back

        Returns:
            List of Observation objects
        """
        if not self.reflection_log_path.exists():
            return []

        observations = []
        cutoff = time.time() - (hours * 3600)

        try:
            with open(self.reflection_log_path, 'r') as f:
                content = f.read()

            # Split by cycle separator
            cycles = content.split('---\n')

            for cycle_text in cycles:
                cycle_text = cycle_text.strip()
                if not cycle_text:
                    continue

                try:
                    cycle_data = json.loads(cycle_text)
                except json.JSONDecodeError:
                    continue

                # Check if cycle is recent enough
                cycle_timestamp = cycle_data.get('timestamp', 0)
                # Ensure timestamp is numeric (float or int) for comparison
                try:
                    cycle_timestamp = float(cycle_timestamp)
                except (ValueError, TypeError):
                    cycle_timestamp = 0
                if cycle_timestamp < cutoff:
                    continue

                # Extract insights from cycle
                insights = cycle_data.get('insights', [])
                for insight in insights:
                    obs = Observation(
                        id=f"log_{insight.get('id', int(cycle_timestamp))}",
                        timestamp=cycle_timestamp,
                        phase=insight.get('phase', 1),
                        insight_type=insight.get('insight_type', 'general'),
                        title=insight.get('title', ''),
                        content=insight.get('content', ''),
                        confidence=insight.get('confidence', 0.5),
                        keywords=insight.get('keywords', []),
                        source='reflection_log'
                    )
                    observations.append(obs)

        except Exception as e:
            print(f"[observations] Error parsing reflection log: {e}")

        return observations

    def _deduplicate(self, observations: List[Observation]) -> List[Observation]:
        """
        Remove duplicate observations based on title similarity.

        Args:
            observations: List of observations

        Returns:
            Deduplicated list
        """
        seen_titles = set()
        unique_obs = []

        for obs in observations:
            # Simple deduplication by exact title match
            title_lower = obs.title.lower()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_obs.append(obs)

        return unique_obs

    def _extract_patterns(self, observations: List[Observation]) -> List[Dict[str, Any]]:
        """
        Extract recurring patterns from observations.

        Args:
            observations: List of observations

        Returns:
            List of pattern dictionaries
        """
        patterns = []

        # Count keywords
        all_keywords = []
        for obs in observations:
            all_keywords.extend(obs.keywords)

        keyword_counts = Counter(all_keywords)
        top_keywords = keyword_counts.most_common(10)

        # Count insight types
        type_counts = Counter(o.insight_type for o in observations)

        # Calculate confidence trend (last 7 days)
        now = time.time()
        week_ago = now - (7 * 86400)
        recent_obs = [o for o in observations if o.timestamp > week_ago]

        if recent_obs:
            avg_confidence = sum(o.confidence for o in recent_obs) / len(recent_obs)
        else:
            avg_confidence = 0.0

        patterns.append({
            'type': 'keyword_frequency',
            'title': 'Most Common Topics',
            'data': [{'keyword': k, 'count': c} for k, c in top_keywords],
            'timestamp': now
        })

        patterns.append({
            'type': 'insight_types',
            'title': 'Observation Categories',
            'data': [{'type': t, 'count': c} for t, c in type_counts.most_common()],
            'timestamp': now
        })

        patterns.append({
            'type': 'confidence_trend',
            'title': 'Average Confidence (7 days)',
            'data': {'average': round(avg_confidence, 2), 'sample_size': len(recent_obs)},
            'timestamp': now
        })

        return patterns

    def _group_by_phase(self, observations: List[Observation]) -> Dict[int, List[Dict[str, Any]]]:
        """
        Group observations by analysis phase.

        Args:
            observations: List of observations

        Returns:
            Dictionary mapping phase number to observation list
        """
        grouped = {1: [], 2: [], 3: [], 4: []}

        for obs in observations:
            phase = obs.phase
            if phase in grouped:
                grouped[phase].append(obs.to_dict())

        return grouped

    def _calculate_stats(self, observations: List[Observation]) -> Dict[str, Any]:
        """
        Calculate statistics about observations.

        Args:
            observations: List of observations

        Returns:
            Statistics dictionary
        """
        if not observations:
            return {
                'total_count': 0,
                'avg_confidence': 0.0,
                'top_keywords': [],
                'phase_distribution': {},
                'latest_timestamp': 0
            }

        # Count keywords
        all_keywords = []
        for obs in observations:
            all_keywords.extend(obs.keywords)
        keyword_counts = Counter(all_keywords)
        top_keywords = [k for k, _ in keyword_counts.most_common(5)]

        # Phase distribution
        phase_counts = Counter(o.phase for o in observations)

        return {
            'total_count': len(observations),
            'avg_confidence': round(sum(o.confidence for o in observations) / len(observations), 2),
            'top_keywords': top_keywords,
            'phase_distribution': dict(phase_counts),
            'latest_timestamp': max(o.timestamp for o in observations) if observations else 0
        }


# Global instance
observation_manager = ObservationManager()
