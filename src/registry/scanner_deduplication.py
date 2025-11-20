"""
Scanner result deduplication using content hashing.

Prevents scanners from repeatedly reporting the same issue.
"""
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ScannerDeduplicator:
    def __init__(self, scanner_name: str):
        self.scanner_name = scanner_name
        kloros_home = os.environ.get('KLOROS_HOME', '/home/kloros')
        self.state_file = Path(kloros_home) / ".kloros/scanner_state" / f"{scanner_name}_reported.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()

    def _load_state(self):
        """Load previously reported issue hashes with error recovery."""
        if self.state_file.exists():
            try:
                self.reported = json.loads(self.state_file.read_text())
            except json.JSONDecodeError as e:
                logger.warning(
                    f"[{self.scanner_name}] Corrupted state file detected: {e}. "
                    f"Backing up and resetting state."
                )
                backup_path = self.state_file.with_suffix('.json.corrupt')
                self.state_file.rename(backup_path)
                self.reported = {}
            except Exception as e:
                logger.error(
                    f"[{self.scanner_name}] Failed to load state file: {e}. Resetting state."
                )
                self.reported = {}
        else:
            self.reported = {}

    def _save_state(self):
        """Save reported issue hashes."""
        self.state_file.write_text(json.dumps(self.reported, indent=2))

    def fingerprint(self, finding: Dict[str, Any]) -> str:
        """Generate fingerprint hash for a finding."""
        key_fields = {
            "type": finding.get("type"),
            "daemon": finding.get("daemon"),
            "model": finding.get("model")
        }

        fingerprint_str = json.dumps(key_fields, sort_keys=True)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]

    def should_report(self, finding: Dict[str, Any]) -> bool:
        """Check if finding should be reported (not a duplicate)."""
        fp = self.fingerprint(finding)

        if fp not in self.reported:
            self.reported[fp] = {
                "first_seen": time.time(),
                "last_seen": time.time(),
                "count": 1
            }
            self._save_state()
            return True

        self.reported[fp]["last_seen"] = time.time()
        self.reported[fp]["count"] += 1
        self._save_state()
        return False

    def mark_resolved(self, finding: Dict[str, Any]):
        """Mark a finding as resolved (removes from reported set)."""
        fp = self.fingerprint(finding)
        if fp in self.reported:
            del self.reported[fp]
            self._save_state()
