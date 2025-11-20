"""Text chunking utilities for RAG."""
from typing import List, Optional
import re


def chunk_text(
    text: str,
    tokens: int = 700,
    overlap: int = 80,
    title_path: Optional[str] = None
) -> List[str]:
    """Chunk text into overlapping segments.

    Args:
        text: Text to chunk
        tokens: Target tokens per chunk (uses words as proxy)
        overlap: Token overlap between chunks
        title_path: Optional title/path to prepend to chunks

    Returns:
        List of text chunks
    """
    # Token-agnostic using words as proxy
    # In production, use actual tokenizer
    words = text.split()

    if not words:
        return []

    step = max(1, tokens - overlap)
    chunks = []

    for i in range(0, len(words), step):
        piece = " ".join(words[i:i + tokens])
        if not piece:
            break

        # Add title prefix if provided
        if title_path:
            piece = f"{title_path}\n\n{piece}"

        chunks.append(piece)

    return chunks


def chunk_by_sentences(
    text: str,
    max_sentences: int = 10,
    overlap_sentences: int = 2
) -> List[str]:
    """Chunk text by sentences.

    Args:
        text: Text to chunk
        max_sentences: Maximum sentences per chunk
        overlap_sentences: Sentence overlap between chunks

    Returns:
        List of text chunks
    """
    # Simple sentence split
    sentences = re.split(r'(?<=[.!?])\s+', text)

    if not sentences:
        return []

    chunks = []
    step = max(1, max_sentences - overlap_sentences)

    for i in range(0, len(sentences), step):
        chunk_sents = sentences[i:i + max_sentences]
        chunk = " ".join(chunk_sents)
        if chunk:
            chunks.append(chunk)

    return chunks


def chunk_by_paragraphs(
    text: str,
    max_paragraphs: int = 5,
    overlap_paragraphs: int = 1
) -> List[str]:
    """Chunk text by paragraphs.

    Args:
        text: Text to chunk
        max_paragraphs: Maximum paragraphs per chunk
        overlap_paragraphs: Paragraph overlap between chunks

    Returns:
        List of text chunks
    """
    # Split by double newlines (paragraphs)
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    if not paragraphs:
        return []

    chunks = []
    step = max(1, max_paragraphs - overlap_paragraphs)

    for i in range(0, len(paragraphs), step):
        chunk_paras = paragraphs[i:i + max_paragraphs]
        chunk = "\n\n".join(chunk_paras)
        if chunk:
            chunks.append(chunk)

    return chunks


def smart_chunk(
    text: str,
    target_size: int = 700,
    overlap: int = 80,
    prefer_boundaries: bool = True
) -> List[str]:
    """Smart chunking that respects paragraph boundaries.

    Args:
        text: Text to chunk
        target_size: Target chunk size in tokens (word proxy)
        overlap: Overlap in tokens
        prefer_boundaries: Try to break at paragraph boundaries

    Returns:
        List of text chunks
    """
    if not prefer_boundaries:
        return chunk_text(text, target_size, overlap)

    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    chunks = []
    current_chunk = []
    current_size = 0

    for para in paragraphs:
        para_size = len(para.split())

        # If adding this paragraph exceeds target, start new chunk
        if current_size + para_size > target_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            # Keep last paragraph for overlap if configured
            if overlap > 0 and current_chunk:
                current_chunk = [current_chunk[-1]]
                current_size = len(current_chunk[0].split())
            else:
                current_chunk = []
                current_size = 0

        current_chunk.append(para)
        current_size += para_size

    # Add final chunk
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks
