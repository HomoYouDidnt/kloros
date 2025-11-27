#!/usr/bin/env python3
"""
Timeline Extractor - Component Evolution History from Documentation

Reads documentation and extracts timeline of component development:
- When components were created
- When they were modified/replaced
- Current state vs historical state
- Evolution of architecture

Commits timeline to RAG so KLoROS knows:
- "Was this component replaced?"
- "What's the current architecture?"
- "Why was X deprecated?"

Governance:
- Tool-Integrity: Read-only doc access, safe RAG writes
- D-REAM-Allowed-Stack: File I/O, date parsing, RAG integration
- Preserves historical context for decision-making
"""

import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict

from src.observability.introspection.documentation_catalog import DocumentCatalog

logger = logging.getLogger(__name__)


@dataclass
class ComponentEvent:
    """A single event in component timeline."""
    component_name: str
    event_type: str  # created, modified, replaced, deprecated, removed
    date: str  # ISO format
    description: str
    source_doc: str  # Which doc this came from
    evidence: List[str] = field(default_factory=list)


@dataclass
class ComponentTimeline:
    """Timeline of a component's evolution."""
    component_name: str
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    current_state: str = "unknown"  # active, deprecated, replaced, removed
    replacement: Optional[str] = None  # What replaced this component
    events: List[ComponentEvent] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON/RAG."""
        return {
            "component_name": self.component_name,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "current_state": self.current_state,
            "replacement": self.replacement,
            "events": [asdict(e) for e in self.events]
        }

    def to_narrative(self) -> str:
        """Generate human-readable narrative."""
        lines = [f"# {self.component_name} - Evolution Timeline\n"]

        lines.append(f"**Current State:** {self.current_state}")
        if self.replacement:
            lines.append(f"**Replaced By:** {self.replacement}")

        if self.first_seen:
            lines.append(f"**First Seen:** {self.first_seen}")
        if self.last_seen:
            lines.append(f"**Last Seen:** {self.last_seen}")

        lines.append("\n## Timeline:\n")

        for event in sorted(self.events, key=lambda e: e.date):
            lines.append(f"- **{event.date}** - {event.event_type.upper()}: {event.description}")
            if event.evidence:
                for evidence in event.evidence[:3]:
                    lines.append(f"  - {evidence}")

        return "\n".join(lines)


class TimelineExtractor:
    """Extract component timeline from documentation."""

    def __init__(self):
        self.catalog = DocumentCatalog()
        self.timelines: Dict[str, ComponentTimeline] = {}
        self._doc_cache: Dict[str, str] = {}  # Cache document content to avoid re-reading

    def _read_doc_cached(self, doc_path: str) -> Optional[str]:
        """Read document with caching to avoid repeated disk I/O."""
        if doc_path in self._doc_cache:
            return self._doc_cache[doc_path]

        try:
            content = Path(doc_path).read_text()
            self._doc_cache[doc_path] = content
            return content
        except Exception as e:
            logger.debug(f"[timeline] Error reading {doc_path}: {e}")
            return None

    def extract_dates(self, content: str) -> List[Tuple[str, str]]:
        """
        Extract dates and their context from content.

        Returns:
            List of (date_str, context) tuples
        """
        dates = []

        # Pattern: **Date:** 2025-10-29
        date_patterns = [
            r'\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})',
            r'Date:\s*(\d{4}-\d{2}-\d{2})',
            r'on\s+(\d{4}-\d{2}-\d{2})',
            r'(\d{4}-\d{2}-\d{2})',
        ]

        for pattern in date_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                date_str = match.group(1)
                # Get context around the date
                start = max(0, match.start() - 100)
                end = min(len(content), match.end() + 100)
                context = content[start:end]
                dates.append((date_str, context))

        return dates

    def extract_component_references(self, content: str) -> List[str]:
        """
        Extract component/service names from content.

        Looks for:
        - *.service names
        - Module names
        - System names (Observer, Orchestrator, etc.)
        """
        components = set()

        # Service names
        components.update(re.findall(r'(\w+(?:-\w+)*\.service)', content))

        # System names (capitalized words) - more specific than module imports
        system_names = re.findall(r'\b(Observer|Orchestrator|ASTRAEA|D-REAM|PHASE|SPICA|Curiosity|Introspection|KLoROS)\b', content)
        components.update(system_names)

        # Filter out noise (common Python modules, generic terms)
        noise = {'os', 'sys', 'json', 'logging', 'pathlib', 'datetime', 'typing',
                'dataclasses', 'collections', 're', 'time', 'Path', 'Dict', 'List',
                'Optional', 'Tuple', 'Any', 'str', 'int', 'bool', 'None'}

        components = {c for c in components if c not in noise and len(c) > 2}

        return sorted(list(components))

    def extract_state_changes(self, content: str, doc_path: str) -> List[ComponentEvent]:
        """
        Extract component state changes from content.

        Looks for:
        - "Status: ✅ COMPLETE"
        - "deprecated", "replaced by", "removed"
        - "disable", "enable"
        """
        events = []

        # Extract dates for context
        dates = self.extract_dates(content)
        default_date = dates[0][0] if dates else datetime.now().strftime("%Y-%m-%d")

        # Pattern: Component was replaced
        replaced_pattern = r'(\w+(?:-\w+)*(?:\.service)?)\s+(?:was|is)\s+replaced\s+by\s+(\w+(?:-\w+)*(?:\.service)?)'
        for match in re.finditer(replaced_pattern, content, re.IGNORECASE):
            old_component = match.group(1)
            new_component = match.group(2)
            events.append(ComponentEvent(
                component_name=old_component,
                event_type="replaced",
                date=default_date,
                description=f"Replaced by {new_component}",
                source_doc=doc_path,
                evidence=[f"Mentioned in {Path(doc_path).name}"]
            ))

        # Pattern: Deprecated
        deprecated_pattern = r'(\w+(?:-\w+)*(?:\.service)?)\s+(?:is|was)?\s*deprecated'
        for match in re.finditer(deprecated_pattern, content, re.IGNORECASE):
            component = match.group(1)
            events.append(ComponentEvent(
                component_name=component,
                event_type="deprecated",
                date=default_date,
                description="Marked as deprecated",
                source_doc=doc_path,
                evidence=[f"Mentioned in {Path(doc_path).name}"]
            ))

        # Pattern: Status: ✅ COMPLETE
        status_pattern = r'\*\*Status:\*\*\s*✅\s*(\w+(?:\s+AND\s+\w+)?)'
        for match in re.finditer(status_pattern, content):
            status = match.group(1)
            # Find component name nearby
            context_start = max(0, match.start() - 200)
            context = content[context_start:match.start()]
            components = self.extract_component_references(context)
            if components:
                for comp in components[:2]:  # Top 2 most likely
                    events.append(ComponentEvent(
                        component_name=comp,
                        event_type="completed",
                        date=default_date,
                        description=f"Status: {status}",
                        source_doc=doc_path,
                        evidence=[f"Status marked in {Path(doc_path).name}"]
                    ))

        # Pattern: Disable/Enable
        disable_pattern = r'disable(?:d|s)?\s+(?:the\s+)?(\w+(?:-\w+)*(?:\.service)?)'
        for match in re.finditer(disable_pattern, content, re.IGNORECASE):
            component = match.group(1)
            if component not in ['the', 'this', 'that']:
                events.append(ComponentEvent(
                    component_name=component,
                    event_type="disabled",
                    date=default_date,
                    description="Disabled",
                    source_doc=doc_path,
                    evidence=[f"Mentioned in {Path(doc_path).name}"]
                ))

        return events

    def build_timeline(self, component_name: str) -> ComponentTimeline:
        """Build timeline for a specific component from all docs."""
        if component_name in self.timelines:
            return self.timelines[component_name]

        timeline = ComponentTimeline(component_name=component_name)

        # Search through all cataloged docs (using cache)
        for doc_path, doc in self.catalog.documents.items():
            content = self._read_doc_cached(doc_path)
            if not content:
                continue

            # Check if component is mentioned
            if component_name.lower() in content.lower():
                # Extract events
                events = self.extract_state_changes(content, doc_path)
                for event in events:
                    if event.component_name == component_name:
                        timeline.events.append(event)

        # Determine current state
        if timeline.events:
            sorted_events = sorted(timeline.events, key=lambda e: e.date)
            timeline.first_seen = sorted_events[0].date
            timeline.last_seen = sorted_events[-1].date

            # Check last event
            last_event = sorted_events[-1]
            if last_event.event_type in ["replaced", "deprecated", "removed", "disabled"]:
                timeline.current_state = last_event.event_type
                # Look for replacement
                if "by" in last_event.description:
                    parts = last_event.description.split("by")
                    if len(parts) > 1:
                        timeline.replacement = parts[1].strip()
            elif last_event.event_type in ["completed", "created", "modified"]:
                timeline.current_state = "active"

        self.timelines[component_name] = timeline
        return timeline

    def build_all_timelines(self, max_components: int = 50) -> Dict[str, ComponentTimeline]:
        """
        Build timelines for all components found in docs.

        Args:
            max_components: Maximum components to process (prevents hang on huge doc sets)

        Returns:
            Dictionary of component timelines
        """
        all_components = set()

        # Extract all component references from catalog (using cache)
        logger.info(f"[timeline] Scanning {len(self.catalog.documents)} documents for components...")
        for idx, (doc_path, doc) in enumerate(self.catalog.documents.items()):
            content = self._read_doc_cached(doc_path)
            if not content:
                continue

            components = self.extract_component_references(content)
            all_components.update(components)

            if (idx + 1) % 10 == 0:
                logger.info(f"[timeline] Scanned {idx + 1}/{len(self.catalog.documents)} docs, found {len(all_components)} components so far")

        logger.info(f"[timeline] Found {len(all_components)} total components in documentation")

        # Limit to prevent hang
        components_to_process = sorted(all_components)[:max_components]
        if len(all_components) > max_components:
            logger.warning(f"[timeline] Limiting to {max_components} components (found {len(all_components)})")

        # Build timeline for each
        for idx, component in enumerate(components_to_process):
            self.build_timeline(component)
            if (idx + 1) % 10 == 0:
                logger.info(f"[timeline] Built {idx + 1}/{len(components_to_process)} timelines")

        logger.info(f"[timeline] ✓ Built {len(self.timelines)} component timelines")
        return self.timelines

    def generate_evolution_summary(self) -> str:
        """Generate markdown summary of all component evolution."""
        lines = ["# KLoROS Component Evolution Timeline\n"]
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

        # Group by state
        by_state = defaultdict(list)
        for timeline in self.timelines.values():
            by_state[timeline.current_state].append(timeline)

        # Active components
        if by_state["active"]:
            lines.append("## 🟢 Active Components\n")
            for timeline in sorted(by_state["active"], key=lambda t: t.component_name):
                lines.append(f"- **{timeline.component_name}** (since {timeline.first_seen})")
                if timeline.events:
                    last_event = sorted(timeline.events, key=lambda e: e.date)[-1]
                    lines.append(f"  - Latest: {last_event.description} ({last_event.date})")

        # Replaced components
        if by_state["replaced"]:
            lines.append("\n## 🔄 Replaced Components\n")
            for timeline in sorted(by_state["replaced"], key=lambda t: t.component_name):
                replacement = timeline.replacement or "unknown"
                lines.append(f"- **{timeline.component_name}** → {replacement}")

        # Deprecated components
        if by_state["deprecated"] or by_state["disabled"]:
            lines.append("\n## ⚠️ Deprecated/Disabled Components\n")
            for timeline in sorted(by_state["deprecated"] + by_state["disabled"], key=lambda t: t.component_name):
                lines.append(f"- **{timeline.component_name}** ({timeline.current_state})")

        return "\n".join(lines)

    def commit_to_rag(self, rag_path: Path = Path("/home/kloros/.kloros/component_timeline.json")) -> bool:
        """
        Commit timeline to RAG-accessible format.

        Args:
            rag_path: Where to save timeline

        Returns:
            True if successful
        """
        try:
            data = {
                "generated_at": datetime.now().isoformat(),
                "timelines": {name: tl.to_dict() for name, tl in self.timelines.items()},
                "summary": self.generate_evolution_summary()
            }

            rag_path.write_text(json.dumps(data, indent=2))
            logger.info(f"[timeline] ✓ Committed {len(self.timelines)} timelines to {rag_path}")
            return True

        except Exception as e:
            logger.error(f"[timeline] Failed to commit to RAG: {e}")
            return False


def build_and_commit_timeline(max_components: int = 50) -> str:
    """
    Main entry point: Build component timeline and commit to RAG.

    Args:
        max_components: Maximum components to process (prevents hang)

    Returns:
        Evolution summary
    """
    try:
        # First, catalog all docs
        catalog = DocumentCatalog()
        logger.info(f"[timeline] Using catalog with {len(catalog.documents)} documents")

        # Build timelines (with limit to prevent hang)
        extractor = TimelineExtractor()
        extractor.build_all_timelines(max_components=max_components)

        # Commit to RAG
        extractor.commit_to_rag()

        # Return summary
        summary = extractor.generate_evolution_summary()
        logger.info(f"[timeline] ✓ Timeline extraction complete")
        return summary

    except Exception as e:
        logger.error(f"[timeline] Timeline extraction failed: {e}")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    summary = build_and_commit_timeline()
    print(summary)
