#!/usr/bin/env python3
"""Memory Database Analysis Script"""
import sqlite3
import json
from datetime import datetime

db_path = '/home/kloros/.kloros/memory.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

report = []
report.append("# Memory Health Report")
report.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
report.append(f"**Database:** {db_path}\n")
report.append("---\n")

# 1. Count records
report.append("## 1. Database Record Counts\n")
cursor.execute("SELECT COUNT(*) FROM events")
event_count = cursor.fetchone()[0]
report.append(f"- **Events:** {event_count}")

cursor.execute("SELECT COUNT(*) FROM episodes")
episode_count = cursor.fetchone()[0]
report.append(f"- **Episodes:** {episode_count}")

cursor.execute("SELECT COUNT(*) FROM episode_summaries")
summary_count = cursor.fetchone()[0]
report.append(f"- **Episode Summaries:** {summary_count}\n")

# 2. Check conversation tracking
report.append("## 2. Conversation Tracking Analysis\n")
cursor.execute("""
SELECT conversation_id, COUNT(*) as events
FROM events
GROUP BY conversation_id
ORDER BY events DESC
LIMIT 20
""")
conv_data = cursor.fetchall()
report.append("**Top 20 Conversations by Event Count:**\n")
report.append("| Conversation ID | Event Count |")
report.append("|----------------|-------------|")
for conv_id, count in conv_data:
    report.append(f"| {conv_id or 'NULL'} | {count} |")
report.append("")

# Check for NULL conversation_ids
cursor.execute("SELECT COUNT(*) FROM events WHERE conversation_id IS NULL")
null_conv_count = cursor.fetchone()[0]
report.append(f"**Events with NULL conversation_id:** {null_conv_count} ({null_conv_count/event_count*100:.1f}%)\n")

# 3. Check episode boundaries
report.append("## 3. Episode Boundary Analysis\n")
cursor.execute("""
SELECT id, conversation_id, start_time, end_time, event_count
FROM episodes
ORDER BY start_time DESC
LIMIT 20
""")
episodes = cursor.fetchall()
report.append("**Most Recent 20 Episodes:**\n")
report.append("| ID | Conv ID | Start Time | End Time | Event Count |")
report.append("|----|---------|------------|----------|-------------|")
for ep_id, conv_id, start, end, ev_count in episodes:
    start_dt = datetime.fromtimestamp(start).strftime('%Y-%m-%d %H:%M:%S') if start else 'NULL'
    end_dt = datetime.fromtimestamp(end).strftime('%Y-%m-%d %H:%M:%S') if end else 'NULL'
    report.append(f"| {ep_id} | {conv_id or 'NULL'} | {start_dt} | {end_dt} | {ev_count} |")
report.append("")

# 4. Find orphaned events
report.append("## 4. Data Integrity Check\n")
cursor.execute("""
SELECT COUNT(*) FROM events e
WHERE NOT EXISTS (
    SELECT 1 FROM episodes ep
    WHERE e.timestamp >= ep.start_time
    AND e.timestamp <= ep.end_time
)
""")
orphaned_count = cursor.fetchone()[0]
report.append(f"**Orphaned Events (not in any episode):** {orphaned_count} ({orphaned_count/event_count*100:.1f}%)\n")

# Check episodes without summaries
cursor.execute("""
SELECT COUNT(*) FROM episodes e
WHERE NOT EXISTS (
    SELECT 1 FROM episode_summaries es
    WHERE es.episode_id = e.id
)
""")
unsummarized_count = cursor.fetchone()[0]
report.append(f"**Episodes without summaries:** {unsummarized_count} ({unsummarized_count/episode_count*100:.1f}%)\n")

# 5. Check recent events for context
report.append("## 5. Recent Activity Patterns\n")
cursor.execute("""
SELECT timestamp, event_type, content
FROM events
ORDER BY timestamp DESC
LIMIT 50
""")
recent_events = cursor.fetchall()

# Count event types in recent activity
event_types = {}
for _, event_type, _ in recent_events:
    event_types[event_type] = event_types.get(event_type, 0) + 1

report.append("**Event Type Distribution (last 50 events):**\n")
report.append("| Event Type | Count | Percentage |")
report.append("|------------|-------|------------|")
for event_type, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True):
    report.append(f"| {event_type} | {count} | {count/50*100:.1f}% |")
report.append("")

# Sample recent events
report.append("**Sample Recent Events (last 10):**\n")
for i, (timestamp, event_type, content) in enumerate(recent_events[:10], 1):
    dt = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    content_preview = content[:100].replace('\n', ' ') + '...' if len(content) > 100 else content.replace('\n', ' ')
    report.append(f"{i}. **{dt}** [{event_type}]: {content_preview}")
report.append("")

# 6. Overall event type distribution
report.append("## 6. Overall Event Type Distribution\n")
cursor.execute("""
SELECT event_type, COUNT(*) as count
FROM events
GROUP BY event_type
ORDER BY count DESC
""")
all_event_types = cursor.fetchall()
report.append("| Event Type | Count | Percentage |")
report.append("|------------|-------|------------|")
for event_type, count in all_event_types:
    report.append(f"| {event_type} | {count} | {count/event_count*100:.1f}% |")
report.append("")

# 7. Episode statistics
report.append("## 7. Episode Statistics\n")
cursor.execute("""
SELECT
    AVG(event_count) as avg_events,
    MIN(event_count) as min_events,
    MAX(event_count) as max_events,
    AVG(end_time - start_time) as avg_duration
FROM episodes
WHERE start_time IS NOT NULL AND end_time IS NOT NULL
""")
stats = cursor.fetchone()
if stats[0]:
    report.append(f"- **Average events per episode:** {stats[0]:.1f}")
    report.append(f"- **Min events per episode:** {stats[1]}")
    report.append(f"- **Max events per episode:** {stats[2]}")
    report.append(f"- **Average episode duration:** {stats[3]:.1f} seconds ({stats[3]/60:.1f} minutes)")
report.append("")

# 8. Summary quality analysis
report.append("## 8. Summary Quality Analysis\n")
cursor.execute("""
SELECT
    e.id,
    e.event_count,
    LENGTH(es.summary_text) as summary_length,
    es.key_topics,
    es.importance_score
FROM episodes e
LEFT JOIN episode_summaries es ON e.id = es.episode_id
ORDER BY e.start_time DESC
LIMIT 10
""")
summaries = cursor.fetchall()
report.append("**Recent Episode Summaries:**\n")
for ep_id, ev_count, sum_len, topics, importance in summaries:
    report.append(f"- **Episode {ep_id}:** {ev_count} events")
    if sum_len:
        report.append(f"  - Summary length: {sum_len} chars")
        report.append(f"  - Topics: {topics or 'N/A'}")
        report.append(f"  - Importance: {importance or 'N/A'}")
    else:
        report.append(f"  - ⚠️ No summary")
    report.append("")

# 9. Issues identified
report.append("## 9. Issues Identified\n")
issues = []
if null_conv_count > 0:
    issues.append(f"- **CRITICAL:** {null_conv_count} events have NULL conversation_id, which may break context tracking")
if orphaned_count > event_count * 0.1:
    issues.append(f"- **HIGH:** {orphaned_count} orphaned events ({orphaned_count/event_count*100:.1f}%) not contained in any episode")
if unsummarized_count > episode_count * 0.2:
    issues.append(f"- **MEDIUM:** {unsummarized_count} episodes ({unsummarized_count/episode_count*100:.1f}%) lack summaries")

if issues:
    for issue in issues:
        report.append(issue)
else:
    report.append("- ✅ No major data integrity issues detected")
report.append("")

# 10. Recommendations
report.append("## 10. Recommendations\n")
if null_conv_count > 0:
    report.append("1. **Fix conversation_id assignment:** Ensure all events are tagged with a valid conversation_id")
if orphaned_count > event_count * 0.1:
    report.append("2. **Review episode boundary logic:** High percentage of orphaned events suggests episode creation/closing issues")
if unsummarized_count > 0:
    report.append("3. **Enable episode summarization:** Summaries are crucial for long-term context retrieval")
report.append("")

conn.close()

# Write report
output_path = '/home/kloros/diagnostics/memory_health_report.md'
with open(output_path, 'w') as f:
    f.write('\n'.join(report))

print(f"Report written to {output_path}")
