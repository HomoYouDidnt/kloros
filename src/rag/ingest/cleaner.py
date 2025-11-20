"""Text cleaning utilities for RAG ingestion."""
import re


def clean_text(text: str) -> str:
    """Clean text for RAG ingestion.

    Args:
        text: Raw text

    Returns:
        Cleaned text
    """
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Reduce excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Dehyphenate (remove hyphens at line breaks)
    text = re.sub(r'-\n', '', text)

    # Remove extra whitespace
    text = re.sub(r' +', ' ', text)

    return text.strip()


def remove_code_blocks(text: str) -> str:
    """Remove code blocks from text.

    Args:
        text: Text with code blocks

    Returns:
        Text with code blocks removed
    """
    # Remove triple backtick blocks
    text = re.sub(r'```[\s\S]*?```', '', text)

    # Remove inline code
    text = re.sub(r'`[^`]+`', '', text)

    return text


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text.

    Args:
        text: Text with irregular whitespace

    Returns:
        Text with normalized whitespace
    """
    # Replace tabs with spaces
    text = text.replace('\t', ' ')

    # Reduce multiple spaces
    text = re.sub(r' +', ' ', text)

    # Reduce multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()
