#!/usr/bin/env python3
"""Export episodic memory summaries to knowledge base for RAG expansion."""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, '/home/kloros')

def export_summaries_to_markdown():
    """Export episode summaries to knowledge base markdown files."""

    db_path = Path('/home/kloros/.kloros/memory.db')
    if not db_path.exists():
        print("[export] No memory database found")
        return 0

    kb_learned = Path('/home/kloros/knowledge_base/learned')
    kb_learned.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Get recent summaries (last 30 days)
    cutoff = datetime.now() - timedelta(days=30)
    cursor.execute("""
        SELECT id, episode_id, summary_text, key_topics, importance_score, created_at
        FROM episode_summaries
        WHERE created_at > ?
        ORDER BY created_at DESC
    """, (cutoff.timestamp(),))

    summaries = cursor.fetchall()
    conn.close()

    if not summaries:
        print("[export] No recent summaries to export")
        return 0

    # Group by date
    by_date = {}
    for summary_id, episode_id, text, topics, importance, created_at in summaries:
        date = datetime.fromtimestamp(created_at).strftime('%Y_%m_%d')
        if date not in by_date:
            by_date[date] = []
        by_date[date].append({
            'text': text,
            'topics': topics,
            'importance': importance,
            'time': datetime.fromtimestamp(created_at).strftime('%H:%M')
        })

    # Write markdown files by date
    files_written = 0
    for date, summaries_list in by_date.items():
        output_file = kb_learned / f"conversations_{date}.md"

        with open(output_file, 'w') as f:
            f.write(f"# Conversation Summaries - {date.replace('_', '-')}\n\n")
            f.write("Episodic memory summaries from KLoROS interactions.\n\n")

            for summary in summaries_list:
                f.write(f"## {summary['time']} - {summary['topics']}\n\n")
                f.write(f"**Importance:** {summary['importance']:.2f}\n\n")
                f.write(f"{summary['text']}\n\n")
                f.write("---\n\n")

        files_written += 1

    print(f"[export] Exported {len(summaries)} summaries to {files_written} markdown files")
    return len(summaries)

if __name__ == '__main__':
    export_summaries_to_markdown()
