"""Generates ACE bullets from successful episodes."""
from typing import Tuple, Optional
import time
import hashlib
from .types import Bullet, Delta, Evidence


class BulletGenerator:
    """Generates context hints from episode analysis."""

    def __init__(self, config: dict = None):
        """Initialize generator.

        Args:
            config: Configuration dict
        """
        self.config = config or {}
        self.min_evidence_score = self.config.get("min_evidence_score", 0.6)

    def propose(self, episode: any) -> Tuple[Delta, Evidence]:
        """Analyze episode and propose new bullets.

        Args:
            episode: EpisodeRecord to analyze

        Returns:
            Tuple of (Delta with new bullets, Evidence supporting them)
        """
        # Extract key patterns from episode
        task_query = episode.task_spec.get("query", "")
        domain = episode.task_spec.get("domain", "general")
        outcome = episode.outcome
        success = outcome.get("success", False)

        bullets_to_add = []

        # Only generate bullets from successful episodes
        if success and len(episode.turns) > 0:
            turn = episode.turns[0]  # Focus on first turn for now

            tool_used = turn.decision.get("tool")
            hints_used = turn.decision.get("hints_used", [])

            # Pattern 1: Tool selection bullet
            if tool_used and turn.verify.get("score", 0) > 0.7:
                bullet_text = self._generate_tool_bullet(task_query, tool_used, domain)
                if bullet_text:
                    bullet_id = self._generate_bullet_id(bullet_text)
                    bullets_to_add.append(Bullet(
                        id=bullet_id,
                        text=bullet_text,
                        tags=["tool_selection", domain],
                        domain=domain,
                        metadata={
                            "source_episode": episode.episode_id,
                            "tool": tool_used
                        }
                    ))

            # Pattern 2: Query pattern bullet
            if outcome.get("metrics", {}).get("score", 0) > 0.8:
                bullet_text = self._generate_pattern_bullet(task_query, outcome, domain)
                if bullet_text:
                    bullet_id = self._generate_bullet_id(bullet_text)
                    bullets_to_add.append(Bullet(
                        id=bullet_id,
                        text=bullet_text,
                        tags=["query_pattern", domain],
                        domain=domain,
                        metadata={
                            "source_episode": episode.episode_id
                        }
                    ))

        # Create evidence
        evidence = Evidence(
            episode_id=episode.episode_id,
            signals={
                "success": success,
                "score": outcome.get("metrics", {}).get("score", 0),
                "turns": len(episode.turns)
            },
            rationale=f"Episode {'succeeded' if success else 'failed'} with {len(episode.turns)} turns",
            confidence=outcome.get("metrics", {}).get("score", 0.5)
        )

        delta = Delta(adds=bullets_to_add, updates=[], removes=[])

        if bullets_to_add:
            print(f"[ace] Generated {len(bullets_to_add)} new bullets from episode {episode.episode_id[:8]}")

        return delta, evidence

    def _generate_tool_bullet(self, query: str, tool: str, domain: str) -> Optional[str]:
        """Generate a tool selection bullet.

        Args:
            query: Original query
            tool: Tool that was successful
            domain: Domain

        Returns:
            Bullet text or None
        """
        # Extract key terms from query
        keywords = self._extract_keywords(query)
        if not keywords:
            return None

        keyword_str = " or ".join(keywords[:3])
        return f"For queries about {keyword_str}, prefer {tool} tool"

    def _generate_pattern_bullet(self, query: str, outcome: dict, domain: str) -> Optional[str]:
        """Generate a query pattern bullet.

        Args:
            query: Original query
            outcome: Episode outcome
            domain: Domain

        Returns:
            Bullet text or None
        """
        # Extract pattern from successful query
        query_lower = query.lower()

        # Pattern: Question words
        if any(q in query_lower for q in ["what", "where", "when", "how"]):
            return f"Questions starting with 'what/where/when/how' in {domain} typically succeed with factual retrieval"

        # Pattern: Commands
        if any(cmd in query_lower for cmd in ["play", "show", "find", "search"]):
            return f"Command queries in {domain} benefit from direct tool execution"

        return None

    def _extract_keywords(self, text: str, max_keywords: int = 5) -> list:
        """Extract key terms from text.

        Args:
            text: Text to analyze
            max_keywords: Maximum keywords to return

        Returns:
            List of keywords
        """
        # Simple keyword extraction (in production, use TF-IDF or similar)
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of"}
        words = text.lower().split()
        keywords = [w for w in words if len(w) > 3 and w not in stopwords]
        return keywords[:max_keywords]

    def _generate_bullet_id(self, text: str) -> str:
        """Generate unique bullet ID from text.

        Args:
            text: Bullet text

        Returns:
            Unique ID
        """
        hash_digest = hashlib.md5(text.encode()).hexdigest()[:12]
        timestamp = int(time.time())
        return f"bullet_{timestamp}_{hash_digest}"
