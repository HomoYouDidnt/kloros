"""ChromaDB-based citation retrieval (stub implementation)."""

def index_bibliography(bib_path, chroma_client_or_path=None, collection_name="citations"):
    """Index bibliography file into ChromaDB.
    
    Args:
        bib_path: Path to bibliography file
        chroma_client_or_path: ChromaDB client or path
        collection_name: Collection name
        
    Raises:
        ImportError: chromadb not installed
    """
    raise ImportError(
        "chromadb is required for citation indexing. "
        "Install with: pip install chromadb"
    )

def query_citations(query_terms, chroma_client_or_path=None, collection_name="citations", top_k=5):
    """Query citations from ChromaDB.
    
    Args:
        query_terms: List of query terms
        chroma_client_or_path: ChromaDB client or path
        collection_name: Collection name
        top_k: Number of results
        
    Returns:
        List of citation dictionaries
        
    Raises:
        ImportError: chromadb not installed
    """
    raise ImportError(
        "chromadb is required for citation querying. "
        "Install with: pip install chromadb"
    )
