"""Semantic cache for RAG and query results with provenance tracking."""
import hashlib
import json
import time
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class CacheEntry:
    """Cached query result with provenance."""

    key: str
    query: str
    sources: List[str]
    answer: str
    timestamp: float
    hits: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "key": self.key,
            "query": self.query,
            "sources": self.sources,
            "answer": self.answer,
            "timestamp": self.timestamp,
            "hits": self.hits,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        """Create from dictionary."""
        return cls(**data)


class SemanticCache:
    """Semantic cache with provenance tracking.

    Caches query results based on semantic content (query + sources).
    Ensures byte-identical results for unchanged queries and sources.
    """

    def __init__(self, cache_path: Optional[str] = None, max_age_seconds: int = 86400):
        """Initialize semantic cache.

        Args:
            cache_path: Path to cache file
            max_age_seconds: Maximum age for cache entries (default: 24 hours)
        """
        self.cache_path = cache_path or os.path.expanduser("~/.kloros/semantic_cache.jsonl")
        self.max_age_seconds = max_age_seconds
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)

        # In-memory index for fast lookup
        self._index: Dict[str, CacheEntry] = {}
        self._load_index()

    def _load_index(self):
        """Load cache index from disk."""
        if not os.path.exists(self.cache_path):
            return

        current_time = time.time()
        with open(self.cache_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = CacheEntry.from_dict(json.loads(line))

                    # Skip expired entries
                    if current_time - entry.timestamp > self.max_age_seconds:
                        continue

                    self._index[entry.key] = entry
                except (json.JSONDecodeError, TypeError):
                    continue

    def compute_key(self, query: str, sources: List[str]) -> str:
        """Compute cache key from query and sources.

        Args:
            query: Query string
            sources: List of source identifiers (file paths, URLs, etc.)

        Returns:
            Cache key (SHA256 hash)
        """
        # Normalize sources (sort for consistency)
        normalized_sources = sorted(sources)

        # Compute hash
        content = query + "|" + "|".join(normalized_sources)
        key = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return key

    def get(self, query: str, sources: List[str]) -> Optional[str]:
        """Get cached answer for query with given sources.

        Args:
            query: Query string
            sources: Source identifiers

        Returns:
            Cached answer or None if not found
        """
        key = self.compute_key(query, sources)

        entry = self._index.get(key)
        if entry is None:
            return None

        # Check expiration
        if time.time() - entry.timestamp > self.max_age_seconds:
            del self._index[key]
            return None

        # Update hit count
        entry.hits += 1

        return entry.answer

    def put(
        self,
        query: str,
        sources: List[str],
        answer: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Store answer in cache.

        Args:
            query: Query string
            sources: Source identifiers
            answer: Answer to cache
            metadata: Optional metadata
        """
        key = self.compute_key(query, sources)

        entry = CacheEntry(
            key=key,
            query=query,
            sources=sources,
            answer=answer,
            timestamp=time.time(),
            hits=0,
            metadata=metadata or {}
        )

        # Update index
        self._index[key] = entry

        # Append to file
        with open(self.cache_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def invalidate(self, query: Optional[str] = None, sources: Optional[List[str]] = None):
        """Invalidate cache entries.

        Args:
            query: Specific query to invalidate (if None, invalidate by sources)
            sources: Sources to invalidate (if None and query given, invalidate that query)
        """
        if query is not None and sources is not None:
            # Invalidate specific entry
            key = self.compute_key(query, sources)
            if key in self._index:
                del self._index[key]

        elif sources is not None:
            # Invalidate all entries using these sources
            to_remove = []
            for key, entry in self._index.items():
                if any(src in entry.sources for src in sources):
                    to_remove.append(key)

            for key in to_remove:
                del self._index[key]

        # Rebuild cache file without invalidated entries
        self._rebuild_cache_file()

    def _rebuild_cache_file(self):
        """Rebuild cache file from in-memory index."""
        with open(self.cache_path, "w", encoding="utf-8") as f:
            for entry in self._index.values():
                f.write(json.dumps(entry.to_dict()) + "\n")

    def clear(self):
        """Clear all cache entries."""
        self._index.clear()
        if os.path.exists(self.cache_path):
            os.remove(self.cache_path)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Statistics dict
        """
        total_hits = sum(entry.hits for entry in self._index.values())

        return {
            "entries": len(self._index),
            "total_hits": total_hits,
            "avg_hits_per_entry": total_hits / len(self._index) if self._index else 0,
            "cache_size_bytes": os.path.getsize(self.cache_path) if os.path.exists(self.cache_path) else 0
        }

    def prune_expired(self):
        """Remove expired entries from cache."""
        current_time = time.time()
        to_remove = []

        for key, entry in self._index.items():
            if current_time - entry.timestamp > self.max_age_seconds:
                to_remove.append(key)

        for key in to_remove:
            del self._index[key]

        if to_remove:
            self._rebuild_cache_file()


# Global cache instance
_cache = SemanticCache()


def cache_key(query: str, sources: List[str]) -> str:
    """Compute cache key (convenience function).

    Args:
        query: Query string
        sources: Source identifiers

    Returns:
        Cache key
    """
    return _cache.compute_key(query, sources)


def get_cached(query: str, sources: List[str]) -> Optional[str]:
    """Get cached result (convenience function).

    Args:
        query: Query string
        sources: Source identifiers

    Returns:
        Cached answer or None
    """
    return _cache.get(query, sources)


def put_cached(
    query: str,
    sources: List[str],
    answer: str,
    metadata: Optional[Dict[str, Any]] = None
):
    """Put result in cache (convenience function).

    Args:
        query: Query string
        sources: Source identifiers
        answer: Answer to cache
        metadata: Optional metadata
    """
    _cache.put(query, sources, answer, metadata)
