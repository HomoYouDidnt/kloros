"""
TOON Question Queue Utilities

Format curiosity question queues with TOON compression for analysis scalability.
Expected 35-45% compression on uniform question records.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


def format_question_queue_toon(questions: List[Dict[str, Any]], use_toon: bool = True) -> str:
    """
    Format question queue with TOON compression.

    Processes uniform question records (processed_questions.jsonl, etc.) into
    compact TOON format for LLM analysis.

    Args:
        questions: List of question records
        use_toon: If True, return TOON format; else JSON

    Returns:
        TOON or JSON formatted string

    Example:
        >>> questions = [
        ...     {"question_id": "enable.memory", "processed_at": 123.45, 
        ...      "intent_sha": "abc123", "evidence_hash": "def456"},
        ...     ...
        ... ]
        >>> toon_str = format_question_queue_toon(questions)
    """
    if not questions:
        return "[]"

    if not use_toon:
        return json.dumps(questions, indent=2)

    try:
        from src.cognition.mind.memory.toon_utils import to_toon
        return to_toon(questions, fallback_json=True)
    except Exception as e:
        logger.warning(f"[toon_questions] TOON formatting failed: {e}")
        return json.dumps(questions, indent=2)


def export_question_queue_snapshot(
    input_path: Path,
    output_path: Path,
    limit: Optional[int] = None,
    use_toon: bool = True
) -> Dict[str, Any]:
    """
    Export question queue snapshot with TOON compression.

    Reads JSONL question queue and exports compact snapshot for analysis.

    Args:
        input_path: Source .jsonl file
        output_path: Destination snapshot file
        limit: Maximum records to include (None = all)
        use_toon: Include TOON-compressed version

    Returns:
        Export metrics (json_bytes, toon_bytes, savings_pct)
    """
    questions = []

    with open(input_path, 'r') as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            if not line.strip():
                continue
            try:
                questions.append(json.loads(line))
            except Exception as e:
                logger.warning(f"[toon_questions] Error parsing line {i}: {e}")
                continue

    logger.info(f"[toon_questions] Loaded {len(questions)} question records")

    # Generate JSON version
    json_str = json.dumps(questions, indent=2)
    json_bytes = len(json_str.encode('utf-8'))

    # Generate TOON version
    toon_str = None
    toon_bytes = 0
    savings_pct = 0

    if use_toon:
        try:
            from src.cognition.mind.memory.toon_utils import to_toon
            toon_str = to_toon(questions, fallback_json=False)
            toon_bytes = len(toon_str.encode('utf-8'))
            savings_pct = int(100 * (1 - toon_bytes / json_bytes))
            logger.info(f"[toon_questions] TOON compression: {json_bytes} → {toon_bytes} bytes ({savings_pct}%)")
        except Exception as e:
            logger.warning(f"[toon_questions] TOON export failed: {e}")

    # Write snapshot
    snapshot = {
        "source_file": str(input_path),
        "record_count": len(questions),
        "questions_json": questions,
    }

    if toon_str:
        snapshot["questions_toon"] = toon_str
        snapshot["toon_format"] = True
        snapshot["compression_stats"] = {
            "json_bytes": json_bytes,
            "toon_bytes": toon_bytes,
            "savings_pct": savings_pct
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(snapshot, f, indent=2)

    logger.info(f"[toon_questions] Snapshot saved to {output_path}")

    return {
        "json_bytes": json_bytes,
        "toon_bytes": toon_bytes,
        "savings_pct": savings_pct,
        "record_count": len(questions)
    }
