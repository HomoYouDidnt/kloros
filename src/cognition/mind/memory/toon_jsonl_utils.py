"""
TOON JSONL Utilities (Tier 4)

Convert massive JSONL logs to TOON format for analysis scalability.
Enables reading 2-3x more historical data within LLM context limits.
"""

from typing import Iterator, Dict, Any, Optional, List
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


def stream_jsonl_as_toon(
    jsonl_path: Path,
    limit: Optional[int] = None,
    offset: int = 0,
    use_toon: bool = True
) -> Iterator[str]:
    """
    Stream JSONL file with optional TOON compression per line.

    Yields TOON-formatted strings for each record, enabling 50-60% compression
    on investigation logs, question tracking, etc.

    Args:
        jsonl_path: Path to .jsonl file
        limit: Maximum number of records to yield
        offset: Number of records to skip
        use_toon: If True, yield TOON format; else JSON

    Yields:
        TOON or JSON strings for each record
    """
    if not jsonl_path.exists():
        raise FileNotFoundError(f"JSONL file not found: {jsonl_path}")

    count = 0
    skipped = 0

    with open(jsonl_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue

            if skipped < offset:
                skipped += 1
                continue

            try:
                record = json.loads(line)

                if use_toon:
                    from src.cognition.mind.memory.toon_utils import to_toon
                    yield to_toon(record, fallback_json=True)
                else:
                    yield line.strip()

                count += 1
                if limit and count >= limit:
                    break

            except Exception as e:
                logger.warning(f"[toon_jsonl] Error processing line: {e}")
                continue


def read_jsonl_tail_toon(
    jsonl_path: Path,
    n_records: int = 100,
    use_toon: bool = True
) -> str:
    """
    Read last N records from JSONL file in TOON format.

    Perfect for analyzing recent investigation history without loading full 60MB file.

    Args:
        jsonl_path: Path to .jsonl file
        n_records: Number of recent records to include
        use_toon: If True, return TOON-compressed format

    Returns:
        TOON or JSON formatted string with recent records
    """
    # Read last N lines efficiently (without loading entire file)
    with open(jsonl_path, 'rb') as f:
        # Seek to end
        f.seek(0, 2)
        file_size = f.tell()

        # Read backwards in chunks to find last N lines
        chunk_size = 8192
        lines = []
        buffer = b''
        position = file_size

        while len(lines) < n_records and position > 0:
            chunk_size = min(chunk_size, position)
            position -= chunk_size
            f.seek(position)
            chunk = f.read(chunk_size)
            buffer = chunk + buffer

            # Split into lines
            temp_lines = buffer.split(b'\n')
            if len(temp_lines) > 1:
                # Keep last partial line in buffer
                buffer = temp_lines[0]
                # Add complete lines
                lines = temp_lines[1:] + lines

        # Take last N non-empty lines
        records = []
        for line in lines[-n_records:]:
            if line.strip():
                try:
                    records.append(json.loads(line.decode('utf-8')))
                except:
                    continue

    if not records:
        return "[]"

    # Format as TOON if requested
    if use_toon:
        try:
            from src.cognition.mind.memory.toon_utils import to_toon
            return to_toon(records, fallback_json=True)
        except Exception as e:
            logger.warning(f"[toon_jsonl] TOON formatting failed: {e}")

    return json.dumps(records, indent=2)


def analyze_jsonl_size_savings(jsonl_path: Path, sample_size: int = 1000) -> Dict[str, Any]:
    """
    Analyze potential TOON compression savings for a JSONL file.

    Samples records and reports compression metrics.

    Args:
        jsonl_path: Path to .jsonl file
        sample_size: Number of records to sample

    Returns:
        {"json_bytes": X, "toon_bytes": Y, "savings_pct": Z, "sample_count": N}
    """
    json_bytes = 0
    toon_bytes = 0
    sample_count = 0

    for toon_line in stream_jsonl_as_toon(jsonl_path, limit=sample_size, use_toon=True):
        toon_bytes += len(toon_line)
        sample_count += 1

    # Re-stream as JSON to get original size
    for json_line in stream_jsonl_as_toon(jsonl_path, limit=sample_size, use_toon=False):
        json_bytes += len(json_line)

    savings_pct = 0
    if json_bytes > 0:
        savings_pct = int(100 * (1 - toon_bytes / json_bytes))

    return {
        "json_bytes": json_bytes,
        "toon_bytes": toon_bytes,
        "savings_pct": savings_pct,
        "sample_count": sample_count,
        "file_path": str(jsonl_path),
        "file_size_mb": jsonl_path.stat().st_size / (1024 * 1024)
    }


def convert_jsonl_to_toon_jsonl(
    input_path: Path,
    output_path: Path,
    batch_size: int = 1000
) -> Dict[str, Any]:
    """
    Convert entire JSONL file to TOON-formatted JSONL.

    WARNING: For large files (60MB+), this can take time. Use for archival/analysis.

    Args:
        input_path: Source .jsonl file
        output_path: Destination TOON-formatted .jsonl file
        batch_size: Records to process per batch

    Returns:
        Conversion metrics
    """
    logger.info(f"[toon_jsonl] Converting {input_path} to TOON format...")

    total_records = 0
    total_json_bytes = 0
    total_toon_bytes = 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as out_f:
        for toon_line in stream_jsonl_as_toon(input_path, use_toon=True):
            out_f.write(toon_line + '\n')
            total_toon_bytes += len(toon_line) + 1
            total_records += 1

            if total_records % batch_size == 0:
                logger.info(f"[toon_jsonl] Converted {total_records} records...")

    # Calculate original size
    total_json_bytes = input_path.stat().st_size

    savings_pct = int(100 * (1 - total_toon_bytes / total_json_bytes))

    metrics = {
        "records_converted": total_records,
        "original_bytes": total_json_bytes,
        "toon_bytes": total_toon_bytes,
        "savings_pct": savings_pct,
        "original_mb": round(total_json_bytes / (1024 * 1024), 2),
        "toon_mb": round(total_toon_bytes / (1024 * 1024), 2)
    }

    logger.info(f"[toon_jsonl] Conversion complete: {metrics['original_mb']}MB → "
               f"{metrics['toon_mb']}MB ({savings_pct}% savings)")

    return metrics
