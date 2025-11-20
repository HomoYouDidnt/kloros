"""
SPICA Base Class - Foundation for SPICA-based evaluators

Provides common functionality for SPICA instances:
- Telemetry recording
- Lineage tracking (parent/generation)
- Configuration management
- Manifest generation
"""
import time
import uuid
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class SpicaTelemetryEvent:
    """Single telemetry event."""
    timestamp: float
    event_type: str
    data: Dict[str, Any]
    spica_id: str


class SpicaBase:
    """
    Base class for SPICA-derived evaluators.

    Provides:
    - Unique SPICA ID generation
    - Telemetry collection
    - Lineage tracking (parent_id, generation)
    - Configuration management
    - Manifest export
    """

    def __init__(
        self,
        spica_id: str,
        domain: str,
        config: Optional[Dict] = None,
        parent_id: Optional[str] = None,
        generation: int = 0,
        mutations: Optional[Dict] = None
    ):
        """
        Initialize SPICA base.

        Args:
            spica_id: Unique identifier for this SPICA instance
            domain: Domain name (e.g., "system_health", "rag", "tts")
            config: Configuration dict
            parent_id: ID of parent SPICA (for lineage tracking)
            generation: Generation number in evolution
            mutations: Dict of mutations applied from parent
        """
        self.spica_id = spica_id
        self.domain = domain
        self.config = config or {}
        self.parent_id = parent_id
        self.generation = generation
        self.mutations = mutations or {}

        self.created_at = time.time()
        self.telemetry: List[SpicaTelemetryEvent] = []
        self.metadata: Dict[str, Any] = {}

        # Record creation event
        self.record_telemetry("spica_created", {
            "domain": domain,
            "generation": generation,
            "parent_id": parent_id,
            "has_mutations": len(mutations) > 0 if mutations else False
        })

    def record_telemetry(self, event_type: str, data: Dict[str, Any]):
        """
        Record a telemetry event.

        Args:
            event_type: Type/name of event
            data: Event data dict
        """
        event = SpicaTelemetryEvent(
            timestamp=time.time(),
            event_type=event_type,
            data=data,
            spica_id=self.spica_id
        )
        self.telemetry.append(event)

    def log_event(self, event_type: str, data: Dict[str, Any]):
        """Alias for record_telemetry (backwards compatibility)."""
        self.record_telemetry(event_type, data)

    def get_manifest(self) -> Dict[str, Any]:
        """
        Generate manifest for this SPICA instance.

        Returns:
            Dict with spica_id, domain, config, lineage, telemetry summary
        """
        return {
            "spica_id": self.spica_id,
            "domain": self.domain,
            "config": self.config,
            "lineage": {
                "parent_id": self.parent_id,
                "generation": self.generation,
                "mutations": self.mutations
            },
            "created_at": self.created_at,
            "telemetry_events": len(self.telemetry),
            "metadata": self.metadata
        }

    def get_telemetry_summary(self) -> Dict[str, Any]:
        """
        Get summary of telemetry events.

        Returns:
            Dict with event counts by type
        """
        event_counts = {}
        for event in self.telemetry:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1

        return {
            "total_events": len(self.telemetry),
            "event_counts": event_counts,
            "first_event": self.telemetry[0].timestamp if self.telemetry else None,
            "last_event": self.telemetry[-1].timestamp if self.telemetry else None
        }

    def export_telemetry(self, output_path: Path):
        """
        Export telemetry to JSONL file.

        Args:
            output_path: Path to output file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            for event in self.telemetry:
                f.write(json.dumps({
                    "timestamp": event.timestamp,
                    "event_type": event.event_type,
                    "data": event.data,
                    "spica_id": event.spica_id
                }) + '\n')

    def set_metadata(self, key: str, value: Any):
        """Set metadata key-value pair."""
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata value by key."""
        return self.metadata.get(key, default)

    def get_lineage_chain(self) -> List[str]:
        """
        Get lineage chain from root to this instance.

        Returns:
            List of SPICA IDs from root ancestor to self
        """
        chain = [self.spica_id]
        if self.parent_id:
            chain.insert(0, self.parent_id)
        return chain

    def __repr__(self) -> str:
        return f"<SpicaBase(id={self.spica_id}, domain={self.domain}, gen={self.generation})>"
