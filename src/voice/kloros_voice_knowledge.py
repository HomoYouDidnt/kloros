#!/usr/bin/env python3
"""KLoROS Voice Knowledge Retrieval Zooid - RAG and semantic search.

This zooid handles:
- RAG pipeline (embedding generation, vector search)
- Library indexing daemon integration
- Semantic search over knowledge base
- Source attribution and relevance scoring

ChemBus Signals:
- Emits: VOICE.KNOWLEDGE.RESULTS (documents, relevance_scores, sources)
- Emits: VOICE.KNOWLEDGE.ERROR (error_type, details)
- Listens: VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST (query, top_k, filters)
"""
from __future__ import annotations

import os
import sys
import time
import signal
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.orchestration.core.umn_bus import UMNPub as ChemPub, UMNSub as ChemSub


try:
    from src.simple_rag import RAG as _RAGClass
except ImportError:
    _RAGClass = None  # type: ignore


class KnowledgeZooid:
    """Knowledge retrieval zooid for RAG and semantic search."""

    def __init__(self):
        self.zooid_name = "kloros-voice-knowledge"
        self.niche = "voice.knowledge"

        self.chem_pub = ChemPub()

        self.running = True
        self.enable_knowledge = int(os.getenv("KLR_ENABLE_KNOWLEDGE", "1"))
        self.rag_bundle_path = os.getenv("KLR_RAG_BUNDLE_PATH")
        self.rag_metadata_path = os.getenv("KLR_RAG_METADATA_PATH")
        self.rag_embeddings_path = os.getenv("KLR_RAG_EMBEDDINGS_PATH")
        self.faiss_index_path = os.getenv("KLR_RAG_FAISS_INDEX_PATH")
        self.default_top_k = int(os.getenv("KLR_RAG_TOP_K", "5"))

        self.rag: Optional[Any] = None
        self.rag_available = False

        self.stats = {
            "total_queries": 0,
            "successful_queries": 0,
            "failed_queries": 0,
            "average_relevance": 0.0,
            "query_times": [],
        }

        print(f"[knowledge] Initialized: enable={self.enable_knowledge}")

    def start(self):
        """Start the Knowledge zooid and subscribe to ChemBus signals."""
        print(f"[knowledge] Starting {self.zooid_name}")

        if not self.enable_knowledge:
            print("[knowledge] Knowledge retrieval disabled via KLR_ENABLE_KNOWLEDGE=0")
            return

        self._init_rag_backend()

        self._subscribe_to_signals()

        self.chem_pub.emit(
            "VOICE.KNOWLEDGE.READY",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "rag_available": self.rag_available,
                "backend": "simple_rag" if self.rag_available else "none",
                "default_top_k": self.default_top_k,
            }
        )

        print(f"[knowledge] {self.zooid_name} ready and listening (RAG={self.rag_available})")

    def _init_rag_backend(self) -> None:
        """Initialize RAG backend based on configuration."""
        if _RAGClass is None:
            print("[knowledge] RAG module not available (src.simple_rag not found)")
            self.rag_available = False
            return

        try:
            if self.rag_bundle_path:
                if Path(self.rag_bundle_path).exists():
                    self.rag = _RAGClass(bundle_path=self.rag_bundle_path)
                    print(f"[knowledge] ✅ Loaded RAG from bundle: {self.rag_bundle_path}")
                else:
                    print(f"[knowledge] ⚠️  Bundle path not found: {self.rag_bundle_path}")
                    self.rag_available = False
                    return

            elif self.rag_metadata_path and self.rag_embeddings_path:
                if Path(self.rag_metadata_path).exists() and Path(self.rag_embeddings_path).exists():
                    self.rag = _RAGClass(
                        metadata_path=self.rag_metadata_path,
                        embeddings_path=self.rag_embeddings_path
                    )
                    print(f"[knowledge] ✅ Loaded RAG from metadata+embeddings")
                else:
                    print(f"[knowledge] ⚠️  Metadata or embeddings path not found")
                    self.rag_available = False
                    return
            else:
                print("[knowledge] ⚠️  No RAG paths configured (KLR_RAG_* env vars)")
                self.rag_available = False
                return

            if self.faiss_index_path and Path(self.faiss_index_path).exists():
                try:
                    import faiss
                    idx = faiss.read_index(self.faiss_index_path)
                    if self.rag is not None:
                        self.rag.faiss_index = idx
                    print(f"[knowledge] ✅ Loaded FAISS index: {self.faiss_index_path}")
                except Exception as e:
                    print(f"[knowledge] ⚠️  Failed to load FAISS index: {e}")

            self.rag_available = True

        except Exception as e:
            print(f"[knowledge] ❌ Failed to initialize RAG backend: {e}")
            print(f"[knowledge] Error details: {traceback.format_exc()}")
            self.rag_available = False

    def _subscribe_to_signals(self):
        """Subscribe to ChemBus signals for knowledge requests."""
        self.knowledge_request_sub = ChemSub(
            "VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST",
            self._on_knowledge_request,
            zooid_name=self.zooid_name,
            niche=self.niche
        )

        print("[knowledge] Subscribed to ChemBus signals")

    def _on_knowledge_request(self, event: dict):
        """Handle VOICE.ORCHESTRATOR.KNOWLEDGE.REQUEST signal and perform retrieval.

        Args:
            event: ChemBus event with knowledge request
                - facts.query: Query text for semantic search
                - facts.top_k: Number of documents to retrieve (default: 5)
                - facts.filters: Optional filters for search
                - facts.embedder: Optional embedder callable (not used via ChemBus)
                - incident_id: Event correlation ID
        """
        if not self.running:
            return

        try:
            facts = event.get("facts", {})
            query = facts.get("query", "")
            top_k = facts.get("top_k", self.default_top_k)
            filters = facts.get("filters", {})
            incident_id = event.get("incident_id")

            if not query:
                print("[knowledge] ERROR: No query in KNOWLEDGE.REQUEST event")
                self._emit_error("missing_query", "No query provided in request", incident_id)
                return

            if not self.rag_available or self.rag is None:
                print(f"[knowledge] RAG not available, sending empty results for: {query[:60]}")

                start_time = time.time()
                query_time = time.time() - start_time

                self.stats["query_times"].append(query_time)
                if len(self.stats["query_times"]) > 100:
                    self.stats["query_times"] = self.stats["query_times"][-100:]

                self.stats["total_queries"] += 1
                self.stats["successful_queries"] += 1

                self._emit_results(
                    query=query,
                    documents=[],
                    relevance_scores=[],
                    sources=[],
                    metadata={"rag_available": False, "reason": "backend_not_initialized"},
                    incident_id=incident_id
                )
                return

            start_time = time.time()

            results = self._perform_retrieval(query, top_k, filters)

            query_time = time.time() - start_time
            self.stats["query_times"].append(query_time)
            if len(self.stats["query_times"]) > 100:
                self.stats["query_times"] = self.stats["query_times"][-100:]

            self.stats["total_queries"] += 1
            self.stats["successful_queries"] += 1

            if results["relevance_scores"]:
                avg_rel = sum(results["relevance_scores"]) / len(results["relevance_scores"])
                old_avg = self.stats["average_relevance"]
                total = self.stats["successful_queries"]
                self.stats["average_relevance"] = (old_avg * (total - 1) + avg_rel) / total

            self._emit_results(
                query=query,
                documents=results["documents"],
                relevance_scores=results["relevance_scores"],
                sources=results["sources"],
                metadata={
                    "query_time": query_time,
                    "top_k": top_k,
                    "filters": filters,
                    "rag_available": True,
                },
                incident_id=incident_id
            )

            print(f"[knowledge] Retrieved ({query_time:.3f}s): {len(results['documents'])} docs for '{query[:60]}'")

        except Exception as e:
            print(f"[knowledge] ERROR during retrieval: {e}")
            print(f"[knowledge] Traceback: {traceback.format_exc()}")
            self.stats["failed_queries"] += 1
            self._emit_error("retrieval_failed", str(e), event.get("incident_id"))

    def _perform_retrieval(self, query: str, top_k: int, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Perform semantic search using RAG backend.

        Args:
            query: Query text
            top_k: Number of documents to retrieve
            filters: Optional filters for search

        Returns:
            Dictionary with documents, relevance_scores, sources
        """
        if self.rag is None:
            return {"documents": [], "relevance_scores": [], "sources": []}

        try:
            if hasattr(self.rag, 'search'):
                search_results = self.rag.search(query, top_k=top_k)
            elif hasattr(self.rag, 'query'):
                search_results = self.rag.query(query, top_k=top_k)
            else:
                print("[knowledge] RAG backend has no search/query method, returning empty")
                return {"documents": [], "relevance_scores": [], "sources": []}

            documents = []
            relevance_scores = []
            sources = []

            if isinstance(search_results, list):
                for result in search_results[:top_k]:
                    if isinstance(result, dict):
                        documents.append(result.get("text", result.get("content", "")))
                        relevance_scores.append(result.get("score", result.get("relevance", 0.0)))
                        sources.append(result.get("source", result.get("metadata", {})))
                    elif isinstance(result, tuple):
                        documents.append(result[0] if len(result) > 0 else "")
                        relevance_scores.append(result[1] if len(result) > 1 else 0.0)
                        sources.append(result[2] if len(result) > 2 else {})
            elif isinstance(search_results, dict):
                documents = search_results.get("documents", search_results.get("texts", []))
                relevance_scores = search_results.get("scores", search_results.get("relevance", []))
                sources = search_results.get("sources", search_results.get("metadata", []))

            return {
                "documents": documents[:top_k],
                "relevance_scores": relevance_scores[:top_k],
                "sources": sources[:top_k] if sources else [{} for _ in documents[:top_k]]
            }

        except Exception as e:
            print(f"[knowledge] RAG search failed: {e}")
            return {"documents": [], "relevance_scores": [], "sources": []}

    def _emit_results(
        self,
        query: str,
        documents: list,
        relevance_scores: list,
        sources: list,
        metadata: dict,
        incident_id: Optional[str]
    ):
        """Emit VOICE.KNOWLEDGE.RESULTS signal.

        Args:
            query: Original query
            documents: Retrieved documents
            relevance_scores: Relevance scores for each document
            sources: Source metadata for each document
            metadata: Additional metadata (query_time, filters, etc.)
            incident_id: Event correlation ID
        """
        self.chem_pub.emit(
            "VOICE.KNOWLEDGE.RESULTS",
            ecosystem="voice",
            intensity=1.0 if documents else 0.5,
            facts={
                "query": query,
                "documents": documents,
                "relevance_scores": relevance_scores,
                "sources": sources,
                "count": len(documents),
                "metadata": metadata,
                "timestamp": datetime.now().isoformat(),
            },
            incident_id=incident_id
        )

    def _emit_error(self, error_type: str, details: str, incident_id: Optional[str]):
        """Emit VOICE.KNOWLEDGE.ERROR signal.

        Args:
            error_type: Type of error (missing_query, retrieval_failed, etc.)
            details: Error details
            incident_id: Event correlation ID
        """
        self.chem_pub.emit(
            "VOICE.KNOWLEDGE.ERROR",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "error_type": error_type,
                "details": details,
                "rag_available": self.rag_available,
                "timestamp": datetime.now().isoformat(),
            },
            incident_id=incident_id
        )

    def get_stats(self) -> dict:
        """Get knowledge retrieval statistics.

        Returns:
            Dictionary with query statistics
        """
        avg_query_time = (
            sum(self.stats["query_times"]) / len(self.stats["query_times"])
            if self.stats["query_times"] else 0.0
        )

        return {
            **self.stats,
            "average_query_time": avg_query_time,
            "rag_available": self.rag_available,
        }

    def shutdown(self):
        """Graceful shutdown of Knowledge zooid."""
        print(f"[knowledge] Shutting down {self.zooid_name}")
        self.running = False

        final_stats = self.get_stats()
        print(f"[knowledge] Final statistics: {final_stats}")

        self.chem_pub.emit(
            "VOICE.KNOWLEDGE.SHUTDOWN",
            ecosystem="voice",
            intensity=1.0,
            facts={
                "zooid": self.zooid_name,
                "stats": final_stats,
            }
        )

        if hasattr(self, 'knowledge_request_sub'):
            self.knowledge_request_sub.close()
        self.chem_pub.close()

        print(f"[knowledge] {self.zooid_name} shutdown complete")


def main():
    """Main entry point for Knowledge zooid daemon."""
    print("[knowledge] Starting KLoROS Voice Knowledge Retrieval Zooid")

    zooid = KnowledgeZooid()

    def signal_handler(signum, frame):
        print(f"[knowledge] Received signal {signum}, shutting down...")
        zooid.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    zooid.start()

    try:
        while zooid.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[knowledge] Interrupted by user")
    finally:
        zooid.shutdown()


if __name__ == "__main__":
    main()
