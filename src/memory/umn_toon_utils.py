"""
UMN TOON Utilities - Extract and decode TOON-formatted UMN messages.

Provides helper functions to extract facts from UMN messages, automatically
detecting and decoding TOON format when available, with graceful fallback to JSON.
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def extract_facts(msg: Dict[str, Any], prefer_toon: bool = True) -> Dict[str, Any]:
    """
    Extract facts from UMN message, intelligently choosing TOON or JSON.

    Args:
        msg: UMN message dictionary
        prefer_toon: If True, use facts_toon when available

    Returns:
        Facts dictionary (decoded from TOON if available, else JSON)

    Example:
        >>> msg = {"facts": {"a": 1}, "facts_toon": "[1]{a}:1", "toon_format": True}
        >>> extract_facts(msg)
        {'a': 1}  # Decoded from TOON format
    """
    # Check if message has TOON-encoded facts
    if prefer_toon and msg.get('toon_format') and 'facts_toon' in msg:
        try:
            from src.cognition.mind.memory.toon_utils import from_toon
            facts = from_toon(msg['facts_toon'], fallback_json=True)
            logger.debug(f"[chem_toon] Decoded facts from TOON format")
            return facts
        except Exception as e:
            logger.warning(f"[chem_toon] TOON decode failed, using JSON facts: {e}")

    # Fallback to standard JSON facts
    return msg.get('facts', {})


def get_facts_with_format_info(msg: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
    """
    Extract facts and report which format was used.

    Returns:
        (facts_dict, format_used) where format_used is "toon" or "json"
    """
    if msg.get('toon_format') and 'facts_toon' in msg:
        try:
            from src.cognition.mind.memory.toon_utils import from_toon
            facts = from_toon(msg['facts_toon'], fallback_json=False)
            return facts, "toon"
        except Exception:
            pass

    return msg.get('facts', {}), "json"
