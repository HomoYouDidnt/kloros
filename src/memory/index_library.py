#!/usr/bin/env python3
"""
Index the knowledge library into KOSMOS.

Scans /mnt/storage/kloros/KOSMOS for .md, .txt, .py files and indexes them.
"""

import logging
import sys
from pathlib import Path
from typing import List

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.cognition.mind.memory.kosmos import get_kosmos


LIBRARY_ROOT = Path("/mnt/storage/kloros/KOSMOS")
INDEXABLE_EXTENSIONS = {'.md', '.txt', '.py', '.yaml', '.yml', '.json', '.toml'}


def find_indexable_files(root: Path) -> List[Path]:
    """
    Find all indexable files in library.

    Args:
        root: Root directory to scan

    Returns:
        List of Path objects for indexable files
    """
    files = []

    if not root.exists():
        logger.error(f"Library root does not exist: {root}")
        return files

    for path in root.rglob('*'):
        if path.is_file() and path.suffix.lower() in INDEXABLE_EXTENSIONS:
            files.append(path)

    logger.info(f"Found {len(files)} indexable files in {root}")
    return files


def index_library(force_reindex: bool = False):
    """
    Index all library files into KOSMOS.

    Args:
        force_reindex: If True, reindex all files even if already indexed
    """
    logger.info("Starting library indexing...")

    # Get KOSMOS instance
    kosmos = get_kosmos()
    if kosmos is None:
        logger.error("Failed to initialize KOSMOS")
        return

    # Find files to index
    files = find_indexable_files(LIBRARY_ROOT)

    if not files:
        logger.warning("No files found to index")
        return

    # Index each file
    indexed_count = 0
    skipped_count = 0
    failed_count = 0

    for file_path in files:
        try:
            # Check if already indexed and up-to-date
            if not force_reindex and kosmos.is_indexed(file_path):
                if not kosmos.is_stale(file_path):
                    logger.debug(f"Skipping up-to-date file: {file_path}")
                    skipped_count += 1
                    continue

            # Index the file
            result = kosmos.summarize_and_index(file_path)

            if result['success']:
                logger.info(f"✓ Indexed: {file_path.relative_to(LIBRARY_ROOT)}")
                indexed_count += 1
            else:
                logger.warning(f"✗ Failed: {file_path.relative_to(LIBRARY_ROOT)} - {result.get('error', 'Unknown error')}")
                failed_count += 1

        except Exception as e:
            logger.error(f"✗ Error indexing {file_path}: {e}")
            failed_count += 1

    # Summary
    logger.info("=" * 60)
    logger.info(f"Indexing complete:")
    logger.info(f"  Indexed: {indexed_count}")
    logger.info(f"  Skipped (up-to-date): {skipped_count}")
    logger.info(f"  Failed: {failed_count}")
    logger.info(f"  Total files: {len(files)}")
    logger.info("=" * 60)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Index knowledge library into KOSMOS')
    parser.add_argument('--force', action='store_true', help='Force reindex all files')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        index_library(force_reindex=args.force)
    except KeyboardInterrupt:
        logger.info("\nIndexing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
