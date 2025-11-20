"""
Cache-to-Cache (C2C) Manager for KLoROS

Implements semantic communication between LLM subsystems via context transfer.
Based on: "Cache-To-Cache: Direct Semantic Communication Between LLMs"
https://arxiv.org/pdf/2510.03215

Architecture:
    Voice System (Qwen 7B) → saves context
    Reflection System (Qwen 14B) → loads context
    Result: Zero-token semantic transfer
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

CACHE_DIR = Path("/home/kloros/.kloros/c2c_caches")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

class ContextCache:
    """Represents a cached LLM context state."""

    def __init__(
        self,
        context_tokens: List[int],
        source_model: str,
        source_subsystem: str,
        topic: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.context_tokens = context_tokens
        self.source_model = source_model
        self.source_subsystem = source_subsystem
        self.topic = topic
        self.metadata = metadata or {}
        self.timestamp = datetime.now()
        self.cache_id = self._generate_id()

    def _generate_id(self) -> str:
        """Generate unique cache ID."""
        content = f"{self.source_subsystem}:{self.topic}:{self.timestamp.isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize cache to dict."""
        return {
            "cache_id": self.cache_id,
            "context_tokens": self.context_tokens,
            "source_model": self.source_model,
            "source_subsystem": self.source_subsystem,
            "topic": self.topic,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "token_count": len(self.context_tokens)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextCache":
        """Deserialize cache from dict."""
        cache = cls(
            context_tokens=data["context_tokens"],
            source_model=data["source_model"],
            source_subsystem=data["source_subsystem"],
            topic=data["topic"],
            metadata=data.get("metadata", {})
        )
        cache.timestamp = datetime.fromisoformat(data["timestamp"])
        cache.cache_id = data["cache_id"]
        return cache

    def is_stale(self, max_age_minutes: int = 60) -> bool:
        """Check if cache is too old."""
        age = datetime.now() - self.timestamp
        return age > timedelta(minutes=max_age_minutes)

    def save(self) -> Path:
        """Save cache to disk."""
        cache_file = CACHE_DIR / f"{self.cache_id}.json"
        with open(cache_file, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"[C2C] Saved cache {self.cache_id} ({len(self.context_tokens)} tokens)")
        return cache_file


class C2CManager:
    """
    Manages context transfer between KLoROS subsystems.

    Usage:
        # Voice system saves context
        manager = C2CManager()
        manager.save_context(
            context_tokens=ollama_response['context'],
            source_subsystem='voice',
            topic='codebase_analysis'
        )

        # Reflection system loads context
        context = manager.load_context(
            subsystem='voice',
            topic='codebase_analysis'
        )
        # Use context in next Ollama call
    """

    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def save_context(
        self,
        context_tokens: List[int],
        source_model: str,
        source_subsystem: str,
        topic: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Save LLM context for later retrieval.

        Args:
            context_tokens: Token array from Ollama response['context']
            source_model: Model that generated context (e.g., 'qwen2.5:7b')
            source_subsystem: KLoROS subsystem (e.g., 'voice', 'reflection', 'd-ream')
            topic: Semantic topic (e.g., 'codebase_analysis', 'error_diagnosis')
            metadata: Optional additional data

        Returns:
            cache_id: Unique identifier for this cache
        """
        cache = ContextCache(
            context_tokens=context_tokens,
            source_model=source_model,
            source_subsystem=source_subsystem,
            topic=topic,
            metadata=metadata
        )
        cache.save()
        return cache.cache_id

    def load_context(
        self,
        subsystem: Optional[str] = None,
        topic: Optional[str] = None,
        cache_id: Optional[str] = None,
        max_age_minutes: int = 60
    ) -> Optional[ContextCache]:
        """
        Load most recent context matching criteria.

        Args:
            subsystem: Filter by source subsystem
            topic: Filter by topic
            cache_id: Load specific cache by ID
            max_age_minutes: Reject caches older than this

        Returns:
            ContextCache or None if not found
        """
        if cache_id:
            cache_file = self.cache_dir / f"{cache_id}.json"
            if cache_file.exists():
                with open(cache_file) as f:
                    return ContextCache.from_dict(json.load(f))
            return None

        # Find matching caches
        matches = []
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    cache = ContextCache.from_dict(data)

                    # Apply filters
                    if cache.is_stale(max_age_minutes):
                        continue
                    if subsystem and cache.source_subsystem != subsystem:
                        continue
                    if topic and cache.topic != topic:
                        continue

                    matches.append(cache)
            except Exception as e:
                logger.warning(f"[C2C] Failed to load {cache_file}: {e}")

        if not matches:
            logger.info(f"[C2C] No matching caches (subsystem={subsystem}, topic={topic})")
            return None

        # Return most recent
        matches.sort(key=lambda c: c.timestamp, reverse=True)
        logger.info(f"[C2C] Loaded cache {matches[0].cache_id} ({len(matches[0].context_tokens)} tokens)")
        return matches[0]

    def list_caches(
        self,
        subsystem: Optional[str] = None,
        max_age_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """List available caches with metadata."""
        caches = []
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    cache = ContextCache.from_dict(data)

                    if cache.is_stale(max_age_minutes):
                        continue
                    if subsystem and cache.source_subsystem != subsystem:
                        continue

                    caches.append({
                        "cache_id": cache.cache_id,
                        "subsystem": cache.source_subsystem,
                        "topic": cache.topic,
                        "model": cache.source_model,
                        "tokens": len(cache.context_tokens),
                        "age_minutes": (datetime.now() - cache.timestamp).seconds // 60,
                        "timestamp": cache.timestamp.isoformat()
                    })
            except Exception as e:
                logger.warning(f"[C2C] Failed to read {cache_file}: {e}")

        caches.sort(key=lambda c: c["timestamp"], reverse=True)
        return caches

    def cleanup_stale(self, max_age_minutes: int = 120):
        """Remove caches older than threshold."""
        removed = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    cache = ContextCache.from_dict(data)
                    if cache.is_stale(max_age_minutes):
                        cache_file.unlink()
                        removed += 1
            except Exception as e:
                logger.warning(f"[C2C] Cleanup failed for {cache_file}: {e}")

        if removed > 0:
            logger.info(f"[C2C] Cleaned up {removed} stale caches")
        return removed


def inject_context_into_ollama_call(
    prompt: str,
    model: str,
    manager: C2CManager,
    subsystem: Optional[str] = None,
    topic: Optional[str] = None,
    **ollama_kwargs
) -> Dict[str, Any]:
    """
    Helper: Automatically inject cached context into Ollama API call.

    Args:
        prompt: User prompt
        model: Ollama model name
        manager: C2CManager instance
        subsystem: Load context from this subsystem
        topic: Load context for this topic
        **ollama_kwargs: Additional Ollama API parameters

    Returns:
        dict ready for requests.post('http://localhost:11434/api/generate', json=...)
    """
    payload = {
        "model": model,
        "prompt": prompt,
        **ollama_kwargs
    }

    # Try to load cached context
    if subsystem or topic:
        cache = manager.load_context(subsystem=subsystem, topic=topic)
        if cache:
            payload["context"] = cache.context_tokens
            logger.info(f"[C2C] Injected {len(cache.context_tokens)} tokens from {cache.source_subsystem}")

    return payload


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    manager = C2CManager()

    # Simulate voice system saving context
    fake_context = [151644, 8948, 198] * 100  # Dummy tokens
    cache_id = manager.save_context(
        context_tokens=fake_context,
        source_model="qwen2.5:7b",
        source_subsystem="voice",
        topic="test_topic",
        metadata={"user_query": "What is the system status?"}
    )
    print(f"Saved cache: {cache_id}")

    # Simulate reflection system loading context
    cache = manager.load_context(subsystem="voice", topic="test_topic")
    if cache:
        print(f"Loaded cache: {cache.cache_id} with {len(cache.context_tokens)} tokens")

    # List all caches
    print("\nAvailable caches:")
    for c in manager.list_caches():
        print(f"  {c['subsystem']}/{c['topic']}: {c['tokens']} tokens ({c['age_minutes']}m old)")
