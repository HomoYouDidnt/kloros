#!/usr/bin/env python3
"""
Error Frequency Detector Scanner

Analyzes error patterns in memory to detect:
- Repeated identical errors (same error 10+ times)
- Error storms (high frequency in short time)
- Cyclic errors (same error at same time each day)
- Escalating errors (increasing frequency over time)

Purpose:
Surfaces error patterns that indicate systemic issues rather than
one-off failures. Helps KLoROS notice when she's stuck in a loop
or when a service is consistently failing.

Example:
"Storage folder already accessed" error appearing 100+ times
should trigger investigation of Qdrant file mode issue.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import hashlib

logger = logging.getLogger(__name__)


class ErrorFrequencyScanner:
    """Detects repeated error patterns in memory."""

    def __init__(self):
        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from src.cognition.mind.memory.storage import MemoryStore, EventType

            self.store = MemoryStore()
            self.EventType = EventType
            self.available = True
            logger.info("[error_freq] ✓ Memory system available")
        except Exception as e:
            logger.warning(f"[error_freq] Memory system not available: {e}")
            self.available = False

    def _error_signature(self, error_message: str) -> str:
        """
        Create error signature for grouping similar errors.

        Strips out variable parts (timestamps, PIDs, file paths)
        to group errors by root cause.
        """
        import re

        normalized = error_message.lower()

        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}', '<TIMESTAMP>', normalized)
        normalized = re.sub(r'pid[:\s]+\d+', 'pid <PID>', normalized)
        normalized = re.sub(r'/[^\s]+', '<PATH>', normalized)
        normalized = re.sub(r'\d+', '<NUM>', normalized)
        normalized = re.sub(r'[a-f0-9]{8,}', '<HASH>', normalized)

        signature = hashlib.sha256(normalized.encode()).hexdigest()[:16]
        return signature

    def scan_error_patterns(
        self,
        lookback_hours: int = 24,
        min_occurrences: int = 5
    ) -> List[Dict]:
        """
        Scan for repeated error patterns.

        Args:
            lookback_hours: How far back to look for errors
            min_occurrences: Minimum repetitions to report

        Returns:
            List of error patterns with metadata
        """
        if not self.available:
            logger.warning("[error_freq] Memory not available")
            return []

        cutoff_time = datetime.now() - timedelta(hours=lookback_hours)

        conn = self.store._get_connection()
        cursor = conn.execute("""
            SELECT content, metadata, timestamp
            FROM events
            WHERE event_type IN ('error', 'investigation_completed')
            AND timestamp >= ?
            ORDER BY timestamp DESC
        """, (cutoff_time.isoformat(),))

        events = cursor.fetchall()
        conn.close()

        if not events:
            logger.debug("[error_freq] No errors found in lookback window")
            return []

        error_groups = defaultdict(list)

        for content, metadata_json, timestamp in events:
            import json
            metadata = json.loads(metadata_json) if metadata_json else {}

            error_msg = content
            if 'error' in metadata:
                error_msg = metadata['error']
            elif 'conclusion' in metadata and 'failed' in metadata.get('conclusion', '').lower():
                error_msg = metadata['conclusion']

            sig = self._error_signature(error_msg)

            error_groups[sig].append({
                'message': error_msg,
                'timestamp': timestamp,
                'metadata': metadata,
                'content': content
            })

        patterns = []
        for sig, occurrences in error_groups.items():
            if len(occurrences) < min_occurrences:
                continue

            pattern = self._analyze_pattern(sig, occurrences, lookback_hours)
            if pattern:
                patterns.append(pattern)

        patterns.sort(key=lambda p: p['severity_score'], reverse=True)

        return patterns

    def _analyze_pattern(
        self,
        signature: str,
        occurrences: List[Dict],
        lookback_hours: int
    ) -> Optional[Dict]:
        """Analyze a group of similar errors for patterns."""

        if not occurrences:
            return None

        count = len(occurrences)

        timestamps = [
            datetime.fromisoformat(occ['timestamp'])
            for occ in occurrences
        ]
        timestamps.sort()

        first_seen = timestamps[0]
        last_seen = timestamps[-1]
        duration = (last_seen - first_seen).total_seconds() / 3600

        freq_per_hour = count / max(duration, 0.1)

        severity = 'info'
        severity_score = 0

        if freq_per_hour > 10:
            severity = 'critical'
            severity_score = 100
        elif freq_per_hour > 5:
            severity = 'error'
            severity_score = 75
        elif count > 20:
            severity = 'warning'
            severity_score = 50
        elif count >= 5:
            severity = 'info'
            severity_score = 25

        is_cyclic = self._detect_cyclic_pattern(timestamps)
        if is_cyclic:
            severity_score += 20

        is_escalating = self._detect_escalation(timestamps)
        if is_escalating:
            severity_score += 30

        example_msg = occurrences[0]['message'][:200]

        pattern_type = []
        if freq_per_hour > 10:
            pattern_type.append('error_storm')
        if is_cyclic:
            pattern_type.append('cyclic')
        if is_escalating:
            pattern_type.append('escalating')
        if count > 50:
            pattern_type.append('persistent')

        return {
            'signature': signature,
            'count': count,
            'frequency_per_hour': round(freq_per_hour, 2),
            'first_seen': first_seen.isoformat(),
            'last_seen': last_seen.isoformat(),
            'duration_hours': round(duration, 2),
            'severity': severity,
            'severity_score': severity_score,
            'example_message': example_msg,
            'pattern_types': pattern_type,
            'is_cyclic': is_cyclic,
            'is_escalating': is_escalating,
            'occurrences': occurrences[:10]
        }

    def _detect_cyclic_pattern(self, timestamps: List[datetime]) -> bool:
        """
        Detect if errors happen at same time each day/hour.

        Returns True if errors cluster around same time of day.
        """
        if len(timestamps) < 5:
            return False

        hours_of_day = [ts.hour for ts in timestamps]

        from collections import Counter
        hour_counts = Counter(hours_of_day)

        most_common_hour, occurrences = hour_counts.most_common(1)[0]

        if occurrences >= len(timestamps) * 0.6:
            return True

        return False

    def _detect_escalation(self, timestamps: List[datetime]) -> bool:
        """
        Detect if error frequency is increasing over time.

        Returns True if recent errors are more frequent than earlier ones.
        """
        if len(timestamps) < 10:
            return False

        midpoint = len(timestamps) // 2
        first_half = timestamps[:midpoint]
        second_half = timestamps[midpoint:]

        first_duration = (first_half[-1] - first_half[0]).total_seconds() / 3600
        second_duration = (second_half[-1] - second_half[0]).total_seconds() / 3600

        if first_duration < 0.1 or second_duration < 0.1:
            return False

        first_rate = len(first_half) / first_duration
        second_rate = len(second_half) / second_duration

        if second_rate > first_rate * 1.5:
            return True

        return False

    def format_findings(self, patterns: List[Dict]) -> str:
        """Format error patterns as human-readable report."""

        if not patterns:
            return "✓ No repeated error patterns detected"

        report = []
        report.append(f"⚠️  Detected {len(patterns)} error patterns:\n")

        for idx, pattern in enumerate(patterns[:5], 1):
            severity_icon = {
                'critical': '🔴',
                'error': '🟠',
                'warning': '🟡',
                'info': '🔵'
            }.get(pattern['severity'], '⚪')

            report.append(f"{severity_icon} Pattern {idx}: {pattern['severity'].upper()}")
            report.append(f"   Count: {pattern['count']} occurrences")
            report.append(f"   Frequency: {pattern['frequency_per_hour']}/hour")
            report.append(f"   Duration: {pattern['duration_hours']:.1f} hours")

            if pattern['pattern_types']:
                types = ', '.join(pattern['pattern_types'])
                report.append(f"   Types: {types}")

            report.append(f"   Example: {pattern['example_message']}")
            report.append("")

        if len(patterns) > 5:
            report.append(f"... and {len(patterns) - 5} more patterns")

        return '\n'.join(report)


def scan_for_error_patterns(
    lookback_hours: int = 24,
    min_occurrences: int = 5
) -> Tuple[List[Dict], str]:
    """
    Main entry point: Scan for repeated error patterns.

    Args:
        lookback_hours: How far back to analyze
        min_occurrences: Minimum repetitions to flag

    Returns:
        (patterns, formatted_report)
    """
    scanner = ErrorFrequencyScanner()
    patterns = scanner.scan_error_patterns(lookback_hours, min_occurrences)
    report = scanner.format_findings(patterns)

    return patterns, report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    patterns, report = scan_for_error_patterns(lookback_hours=72, min_occurrences=3)

    print(report)

    if patterns:
        print("\n" + "="*60)
        print("Top Error Pattern Details:")
        print("="*60)
        top = patterns[0]
        print(f"Signature: {top['signature']}")
        print(f"Severity Score: {top['severity_score']}")
        print(f"First occurrence: {top['first_seen']}")
        print(f"Last occurrence: {top['last_seen']}")
        print(f"Pattern types: {', '.join(top['pattern_types'])}")
