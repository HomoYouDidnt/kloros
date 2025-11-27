"""
TOON Formatting Utilities for KLoROS

Provides helper functions to format data structures as TOON for LLM consumption.
Use this when sending structured data to meta-agent or other LLM reasoning components.
"""

from typing import Any, List, Dict
import logging

logger = logging.getLogger(__name__)

try:
    from toon_format import encode, decode
    TOON_AVAILABLE = True
except ImportError:
    TOON_AVAILABLE = False
    logger.warning("[toon_utils] toon_format not available, using JSON fallback")


def to_toon(data: Any, fallback_json: bool = True) -> str:
    """
    Convert Python data structure to TOON format for LLM consumption.
    
    Args:
        data: Python object (dict, list, primitives)
        fallback_json: If True, fallback to JSON when TOON unavailable
    
    Returns:
        TOON-formatted string, or JSON if TOON unavailable and fallback enabled
    """
    if not TOON_AVAILABLE:
        if fallback_json:
            import json
            return json.dumps(data, indent=2)
        raise RuntimeError("toon_format not installed and fallback disabled")
    
    return encode(data)


def from_toon(toon_str: str, fallback_json: bool = True) -> Any:
    """
    Parse TOON-formatted string back to Python objects.
    
    Args:
        toon_str: TOON-formatted string
        fallback_json: If True, attempt JSON parsing if TOON fails
    
    Returns:
        Parsed Python object
    """
    if not TOON_AVAILABLE:
        if fallback_json:
            import json
            return json.loads(toon_str)
        raise RuntimeError("toon_format not installed and fallback disabled")
    
    try:
        return decode(toon_str)
    except Exception as e:
        if fallback_json:
            import json
            logger.warning(f"[toon_utils] TOON decode failed, trying JSON: {e}")
            return json.loads(toon_str)
        raise


def format_kosmos_results(results: List[Dict[str, Any]], use_toon: bool = True) -> str:
    """
    Format KOSMOS search results for LLM consumption.
    
    Args:
        results: List of result dictionaries from kosmos.search_knowledge()
        use_toon: If True, use TOON format; otherwise JSON
    
    Returns:
        Formatted string ready for LLM prompt
    """
    # Simplify results (remove large text fields, keep metadata)
    simplified = []
    for r in results:
        simplified.append({
            'file': r['file_path'].split('/')[-1],  # Just filename
            'similarity': round(r['similarity'], 3),
            'type': r['file_type'],
            'date': r.get('document_date', 'unknown')
        })
    
    if use_toon:
        return to_toon(simplified)
    else:
        import json
        return json.dumps(simplified, indent=2)


def format_curiosity_questions(questions: List[Dict[str, Any]], use_toon: bool = True) -> str:
    """
    Format curiosity questions for LLM review/selection.
    
    Args:
        questions: List of CuriosityQuestion dicts
        use_toon: If True, use TOON format; otherwise JSON
    
    Returns:
        Formatted string ready for LLM prompt
    """
    # Extract key fields for LLM decision-making
    simplified = []
    for q in questions:
        simplified.append({
            'id': q.get('id', 'unknown'),
            'question': q.get('question', ''),
            'value': round(q.get('value_estimate', 0), 2),
            'cost': round(q.get('cost', 0), 2),
            'autonomy': q.get('autonomy', 0),
            'evidence_count': len(q.get('evidence', []))
        })
    
    if use_toon:
        return to_toon(simplified)
    else:
        import json
        return json.dumps(simplified, indent=2)
