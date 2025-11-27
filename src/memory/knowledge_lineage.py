"""
Knowledge Lineage Tracking for KOSMOS

Maintains versioned history of all knowledge indexed into KOSMOS.
Provides audit trail of when information entered the canon and how it evolved.
"""

import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

LINEAGE_LOG_PATH = Path.home() / ".kloros" / "knowledge_lineage.jsonl"


@dataclass
class LineageEvent:
    """Represents a single knowledge lineage event."""
    timestamp: str
    event_type: str  # indexed, reindexed, deleted, conflict_detected
    file_path: str
    version: int
    change_type: str  # new, updated, reindexed
    content_hash: str
    summary_hash: str
    git_commit: Optional[str]
    git_message: Optional[str]
    indexed_by: str
    summary_preview: str  # First 100 chars of summary
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class KnowledgeLineageLog:
    """
    Tracks the historical lineage of all knowledge in KOSMOS.
    
    Provides:
    - Append-only event log (JSON Lines format)
    - Version history tracking
    - Temporal queries ("what did we know on date X?")
    - Change auditing
    """
    
    def __init__(self, log_path: Path = LINEAGE_LOG_PATH):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create log file if it doesn't exist
        if not self.log_path.exists():
            self.log_path.touch()
            logger.info(f"[lineage] Created knowledge lineage log: {self.log_path}")
    
    def log_event(self, event: LineageEvent) -> None:
        """Append event to lineage log."""
        try:
            with open(self.log_path, 'a') as f:
                json.dump(event.to_dict(), f)
                f.write('\n')
            logger.debug(f"[lineage] Logged {event.event_type} for {event.file_path}")
        except Exception as e:
            logger.error(f"[lineage] Failed to log event: {e}")
    
    def get_version_history(self, file_path: str) -> List[LineageEvent]:
        """Get version history for a specific file."""
        events = []
        try:
            with open(self.log_path, 'r') as f:
                for line in f:
                    data = json.loads(line)
                    if data['file_path'] == file_path:
                        events.append(LineageEvent(**data))
        except Exception as e:
            logger.error(f"[lineage] Failed to read version history: {e}")
        
        return sorted(events, key=lambda e: e.timestamp)
    
    def get_events_in_range(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> List[LineageEvent]:
        """Get all lineage events within time range."""
        events = []
        try:
            with open(self.log_path, 'r') as f:
                for line in f:
                    data = json.loads(line)
                    event_time = data['timestamp']
                    
                    if start_time and event_time < start_time:
                        continue
                    if end_time and event_time > end_time:
                        continue
                    
                    events.append(LineageEvent(**data))
        except Exception as e:
            logger.error(f"[lineage] Failed to read events: {e}")
        
        return sorted(events, key=lambda e: e.timestamp)
    
    def get_latest_version(self, file_path: str) -> Optional[LineageEvent]:
        """Get the most recent version of a file."""
        history = self.get_version_history(file_path)
        return history[-1] if history else None
    
    def compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return "sha256:" + hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def compute_summary_hash(self, summary: str) -> str:
        """Compute SHA256 hash of summary."""
        return "sha256:" + hashlib.sha256(summary.encode()).hexdigest()[:16]


def get_lineage_log() -> KnowledgeLineageLog:
    """Get singleton lineage log instance."""
    if not hasattr(get_lineage_log, '_instance'):
        get_lineage_log._instance = KnowledgeLineageLog()
    return get_lineage_log._instance
