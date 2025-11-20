#!/usr/bin/env python3
"""
Artifact cleanup script for D-REAM evolutionary optimization.

Retention policy:
- Keep last 10 experiments per domain
- Keep winners from last 30 days
- Keep promotions from last 90 days
- Compress old artifacts >7 days instead of deleting
"""
import json
import gzip
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple

ARTIFACTS_DIR = Path("/home/kloros/artifacts/dream")
LOG_FILE = Path("/home/kloros/logs/artifact_cleanup.log")
METRICS_FILE = Path("/home/kloros/.kloros/artifact_cleanup_metrics.json")

KEEP_LAST_N_PER_DOMAIN = 10
KEEP_WINNERS_DAYS = 30
KEEP_PROMOTIONS_DAYS = 90
COMPRESS_AFTER_DAYS = 7


def log_message(message: str):
    timestamp = datetime.now().isoformat()
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{timestamp}] {message}\n")
    print(message)


def get_experiment_metadata(artifact_path: Path) -> Dict:
    metadata = {
        'domain': 'unknown',
        'is_winner': False,
        'is_promoted': False,
        'created_at': datetime.fromtimestamp(artifact_path.stat().st_mtime)
    }

    metadata_file = artifact_path / 'metadata.json'
    if metadata_file.exists():
        try:
            with open(metadata_file) as f:
                data = json.load(f)
                metadata['domain'] = data.get('question_id', 'unknown').split('.')[0]
                metadata['is_winner'] = data.get('winner', False)
                metadata['is_promoted'] = data.get('promoted', False)
        except Exception as e:
            log_message(f"Warning: Failed to read metadata from {metadata_file}: {e}")

    return metadata


def should_keep(artifact_path: Path, metadata: Dict, now: datetime) -> bool:
    age_days = (now - metadata['created_at']).days

    if metadata['is_winner'] and age_days <= KEEP_WINNERS_DAYS:
        return True

    if metadata['is_promoted'] and age_days <= KEEP_PROMOTIONS_DAYS:
        return True

    return False


def compress_artifact(artifact_path: Path) -> Tuple[int, int]:
    original_size = 0
    compressed_size = 0

    for file_path in artifact_path.rglob('*'):
        if file_path.is_file() and not file_path.name.endswith('.gz'):
            original_size += file_path.stat().st_size

            gz_path = file_path.with_suffix(file_path.suffix + '.gz')
            if not gz_path.exists():
                try:
                    with open(file_path, 'rb') as f_in:
                        with gzip.open(gz_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    file_path.unlink()
                    compressed_size += gz_path.stat().st_size
                except Exception as e:
                    log_message(f"Warning: Failed to compress {file_path}: {e}")

    return original_size, compressed_size


def cleanup_artifacts():
    if not ARTIFACTS_DIR.exists():
        log_message(f"Artifacts directory does not exist: {ARTIFACTS_DIR}")
        return

    now = datetime.now()
    log_message(f"Starting artifact cleanup at {now.isoformat()}")

    by_domain: Dict[str, List[Tuple[Path, Dict]]] = defaultdict(list)
    to_compress: List[Path] = []
    to_delete: List[Path] = []

    for artifact_path in ARTIFACTS_DIR.iterdir():
        if not artifact_path.is_dir():
            continue

        metadata = get_experiment_metadata(artifact_path)
        age_days = (now - metadata['created_at']).days

        if should_keep(artifact_path, metadata, now):
            if age_days > COMPRESS_AFTER_DAYS:
                to_compress.append(artifact_path)
            by_domain[metadata['domain']].append((artifact_path, metadata))
        else:
            by_domain[metadata['domain']].append((artifact_path, metadata))

    for domain, artifacts in by_domain.items():
        artifacts.sort(key=lambda x: x[1]['created_at'], reverse=True)

        for idx, (artifact_path, metadata) in enumerate(artifacts):
            if idx < KEEP_LAST_N_PER_DOMAIN:
                continue

            if not should_keep(artifact_path, metadata, now):
                to_delete.append(artifact_path)

    total_space_freed = 0
    compressed_count = 0
    deleted_count = 0
    original_size_total = 0
    compressed_size_total = 0

    for artifact_path in to_compress:
        try:
            original_size, compressed_size = compress_artifact(artifact_path)
            original_size_total += original_size
            compressed_size_total += compressed_size
            compressed_count += 1
            log_message(f"Compressed: {artifact_path.name} ({original_size} -> {compressed_size} bytes)")
        except Exception as e:
            log_message(f"Error compressing {artifact_path}: {e}")

    for artifact_path in to_delete:
        try:
            size = sum(f.stat().st_size for f in artifact_path.rglob('*') if f.is_file())
            shutil.rmtree(artifact_path)
            total_space_freed += size
            deleted_count += 1
            log_message(f"Deleted: {artifact_path.name} ({size} bytes)")
        except Exception as e:
            log_message(f"Error deleting {artifact_path}: {e}")

    compression_savings = original_size_total - compressed_size_total
    total_space_freed += compression_savings

    metrics = {
        'timestamp': now.isoformat(),
        'compressed_count': compressed_count,
        'deleted_count': deleted_count,
        'space_freed_bytes': total_space_freed,
        'space_freed_mb': round(total_space_freed / (1024 * 1024), 2),
        'compression_ratio': round(compressed_size_total / original_size_total, 2) if original_size_total > 0 else 0
    }

    with open(METRICS_FILE, 'w') as f:
        json.dump(metrics, f, indent=2)

    log_message(f"Cleanup complete: compressed={compressed_count}, deleted={deleted_count}, freed={metrics['space_freed_mb']}MB")


if __name__ == '__main__':
    try:
        cleanup_artifacts()
    except Exception as e:
        log_message(f"Fatal error during cleanup: {e}")
        raise
