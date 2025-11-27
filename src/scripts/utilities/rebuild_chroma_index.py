#!/usr/bin/env python3
"""Rebuild ChromaDB index from SQLite episodic memory."""

import sys
import os

# Add source directory to path
sys.path.insert(0, '/home/kloros')

from src.memory.storage import MemoryStore
from src.memory.chroma_export import ChromaMemoryExporter

def main():
    print("[rebuild] Starting ChromaDB index rebuild from SQLite...")

    # Initialize memory store
    store = MemoryStore()
    print(f"[rebuild] Memory store initialized")

    # Get total counts
    import sqlite3
    conn = sqlite3.connect('/home/kloros/.kloros/memory.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM events')
    event_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM episode_summaries')
    summary_count = cursor.fetchone()[0]
    conn.close()

    print(f"[rebuild] Found {event_count} events and {summary_count} summaries in SQLite")

    # Initialize ChromaDB exporter
    exporter = ChromaMemoryExporter(store)
    print(f"[rebuild] ChromaDB exporter initialized")

    # Export ALL summaries (use huge time window to get everything)
    # 365 days * 24 hours = 8760 hours (1 year)
    # Use 10 years to be safe: 87600 hours
    print(f"[rebuild] Exporting ALL summaries to ChromaDB...")
    result = exporter.export_recent_summaries(
        hours=87600.0,  # 10 years worth
        min_importance=0.0  # Include everything
    )

    print(f"[rebuild] Export complete:")
    print(f"  - Exported: {result['exported']}")
    print(f"  - Skipped: {result['skipped']}")
    print(f"  - Errors: {len(result.get('errors', []))}")

    if result.get('errors'):
        print(f"[rebuild] Errors encountered:")
        for error in result['errors']:
            print(f"  - {error}")
        return 1

    print(f"[rebuild] ✅ ChromaDB index successfully rebuilt!")
    print(f"[rebuild] All {summary_count} summaries are now searchable.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
