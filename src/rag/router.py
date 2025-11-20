"""RAG routing between general and self-RAG domains."""
from typing import Dict, Any, List, Optional
from .hybrid_retriever import HybridRetriever
from .reranker import rerank_chunks
from . import self_tools


# Keywords that indicate self-RAG queries
SELF_QUERY_KEYWORDS = [
    "kloros",
    "your config",
    "your configuration",
    "your settings",
    "your logs",
    "your reports",
    "what model are you",
    "which model",
    "pipeline",
    "where do you store",
    "where are you",
    "self",
    "system status",
    "current config"
]

# Keywords indicating need for live state
LIVE_STATE_KEYWORDS = [
    "current",
    "now",
    "latest",
    "running",
    "where do you save",
    "last",
    "recent",
    "today",
    "active"
]


class RAGRouter:
    """Routes queries to appropriate RAG domain (general or self)."""

    def __init__(
        self,
        general_retriever: HybridRetriever,
        self_retriever: HybridRetriever,
        config: Optional[Dict[str, Any]] = None
    ):
        """Initialize RAG router.

        Args:
            general_retriever: Retriever for general knowledge
            self_retriever: Retriever for self/system knowledge
            config: Router configuration
        """
        self.general_retriever = general_retriever
        self.self_retriever = self_retriever
        self.config = config or {}

    def route_domain(self, query: str) -> str:
        """Determine if query is for general or self domain.

        Args:
            query: Query string

        Returns:
            Domain name ('general' or 'self')
        """
        query_lower = query.lower()

        # Check for self-query keywords
        for keyword in SELF_QUERY_KEYWORDS:
            if keyword in query_lower:
                return "self"

        return "general"

    def needs_live_state(self, query: str, retrieved_chunks: List[Dict[str, Any]]) -> bool:
        """Check if query needs live system state.

        Args:
            query: Query string
            retrieved_chunks: Already retrieved chunks

        Returns:
            True if live state needed
        """
        query_lower = query.lower()

        for keyword in LIVE_STATE_KEYWORDS:
            if keyword in query_lower:
                return True

        return False

    def route_and_retrieve(
        self,
        query: str,
        top_k: int = 6,
        include_live_state: bool = True
    ) -> Dict[str, Any]:
        """Route query and retrieve relevant information.

        Args:
            query: Query string
            top_k: Number of chunks to retrieve
            include_live_state: Include live system state if needed

        Returns:
            Dict with domain, chunks, live_state (optional)
        """
        domain = self.route_domain(query)

        if domain == "general":
            return self._retrieve_general(query, top_k)
        else:
            return self._retrieve_self(query, top_k, include_live_state)

    def _retrieve_general(self, query: str, top_k: int) -> Dict[str, Any]:
        """Retrieve from general knowledge.

        Args:
            query: Query string
            top_k: Number of chunks

        Returns:
            Retrieval result
        """
        # Retrieve with hybrid search
        chunks = self.general_retriever.retrieve(query, top_k=top_k * 2)

        # Rerank
        chunks = rerank_chunks(query, chunks, top_k=top_k)

        return {
            "domain": "general",
            "chunks": chunks,
            "live_state": None
        }

    def _retrieve_self(
        self,
        query: str,
        top_k: int,
        include_live_state: bool
    ) -> Dict[str, Any]:
        """Retrieve from self/system knowledge.

        Args:
            query: Query string
            top_k: Number of chunks
            include_live_state: Include live system state

        Returns:
            Retrieval result
        """
        # Retrieve from self index
        chunks = self.self_retriever.retrieve(query, top_k=top_k * 2)

        # Rerank
        chunks = rerank_chunks(query, chunks, top_k=top_k)

        # Check if live state needed
        live_state = None
        if include_live_state and self.needs_live_state(query, chunks):
            live_state = self._get_live_state(query)

            # Add live state as chunks
            if "status" in live_state:
                chunks.append({
                    "text": str(live_state["status"]),
                    "meta": {"source": "system_status"},
                    "score": 1.0
                })

            if "files" in live_state:
                for file_info in live_state["files"][:2]:  # Limit to top 2 files
                    chunks.append({
                        "text": file_info.get("text", ""),
                        "meta": {"source": f"self://{file_info['path']}"},
                        "score": 0.9
                    })

        return {
            "domain": "self",
            "chunks": chunks,
            "live_state": live_state
        }

    def _get_live_state(self, query: str) -> Dict[str, Any]:
        """Get live system state.

        Args:
            query: Query string

        Returns:
            Live state dict
        """
        live_state = {}

        # Get system status
        status = self_tools.sys_status(["versions", "paths", "config"])
        live_state["status"] = status

        # Search for relevant files based on query
        query_lower = query.lower()
        files = []

        if any(kw in query_lower for kw in ["log", "logs", "error"]):
            # Search logs
            log_files = self_tools.list_recent_logs(limit=5)
            for log_file in log_files[:2]:
                content = self_tools.fs_read(log_file["path"], byte_limit=10000)
                if "error" not in content:
                    files.append({
                        "path": log_file["path"],
                        "text": content["text"][:1000],  # Preview
                        "type": "log"
                    })

        if any(kw in query_lower for kw in ["config", "configuration", "settings"]):
            # Read config file
            config_path = status["paths"]["config"] + "/config.yaml"
            content = self_tools.fs_read(config_path)
            if "error" not in content:
                files.append({
                    "path": config_path,
                    "text": content["text"],
                    "type": "config"
                })

        live_state["files"] = files

        return live_state


def route_query(
    query: str,
    general_retriever: HybridRetriever,
    self_retriever: HybridRetriever,
    top_k: int = 6,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Convenience function for routing queries.

    Args:
        query: Query string
        general_retriever: General knowledge retriever
        self_retriever: Self knowledge retriever
        top_k: Number of results
        config: Router config

    Returns:
        Retrieval result
    """
    router = RAGRouter(general_retriever, self_retriever, config)
    return router.route_and_retrieve(query, top_k=top_k)
