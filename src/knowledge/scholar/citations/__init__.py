"""Citation retrieval for Scholar PLUS."""
try:
    from .chroma_retriever import index_bibliography, query_citations
except ImportError:
    # Chroma retriever not available, use stubs
    def index_bibliography(*args, **kwargs):
        raise ImportError("chromadb required for citation retrieval. Install with: pip install chromadb")
    
    def query_citations(*args, **kwargs):
        raise ImportError("chromadb required for citation retrieval. Install with: pip install chromadb")

__all__ = ["index_bibliography", "query_citations"]
