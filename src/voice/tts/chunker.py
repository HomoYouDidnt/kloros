import re

def chunk_text(text: str, intent: str = "explain"):
    """Chunk text into natural speech segments.

    Args:
        text: Text to chunk
        intent: Intent type (affects chunking strategy)

    Returns:
        List of text chunks
    """
    # Split on punctuation but keep the punctuation
    parts = re.split(r'([,;:.!?])', text)
    chunks, buf = [], ""

    for p in parts:
        if p is None:
            continue
        buf += p

        # End of sentence - always chunk
        if p in ".!?":
            chunks.append(buf.strip())
            buf = ""
        # Mid-sentence pause - chunk if buffer is long enough
        elif p in ",;:" and len(buf) > 60:
            chunks.append(buf.strip())
            buf = ""

    # Add remaining buffer
    if buf.strip():
        chunks.append(buf.strip())

    return chunks
