"""
Wiki resolver utility for mapping user queries to relevant wiki content.

Provides lexical matching of queries to wiki capabilities and modules,
with caching and structured data extraction from markdown documents.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class WikiItem:
    """Represents a single wiki item (capability or module)."""

    item_type: str
    item_id: str
    drift_status: str
    confidence: float = 1.0
    frontmatter: dict = field(default_factory=dict)
    body_sections: dict = field(default_factory=dict)


@dataclass
class WikiContext:
    """Container for retrieved wiki items."""

    items: list[WikiItem] = field(default_factory=list)


class WikiResolver:
    """Resolves user queries to relevant wiki content with caching."""

    def __init__(self, wiki_dir: str = "/home/kloros/wiki"):
        """Initialize the wiki resolver.

        Args:
            wiki_dir: Path to the wiki directory containing index.json and capability files
        """
        self.wiki_dir = Path(wiki_dir)
        self.index_path = self.wiki_dir / "index.json"
        self.capabilities_dir = self.wiki_dir / "capabilities"

        self._index_cache: Optional[dict] = None
        self._frontmatter_cache: dict[str, dict] = {}
        self._body_cache: dict[str, dict] = {}

    def _load_index(self) -> dict:
        """Load and cache the index.json file.

        Returns:
            Parsed index.json content
        """
        if self._index_cache is None:
            with open(self.index_path) as f:
                self._index_cache = json.load(f)
        return self._index_cache

    def _load_capability_file(self, capability_id: str) -> tuple[dict, dict]:
        """Load frontmatter and body sections from a capability markdown file.

        Args:
            capability_id: The capability identifier (e.g., 'audio.output')

        Returns:
            Tuple of (frontmatter_dict, body_sections_dict)
        """
        if capability_id in self._frontmatter_cache:
            frontmatter = self._frontmatter_cache[capability_id]
            body = self._body_cache.get(capability_id, {})
            return frontmatter, body

        capability_file = self.capabilities_dir / f"{capability_id}.md"

        if not capability_file.exists():
            return {}, {}

        content = capability_file.read_text()
        frontmatter, body_text = self._parse_markdown(content)

        self._frontmatter_cache[capability_id] = frontmatter

        body_sections = self._extract_sections(body_text)
        self._body_cache[capability_id] = body_sections

        return frontmatter, body_sections

    @staticmethod
    def _parse_markdown(content: str) -> tuple[dict, str]:
        """Parse YAML frontmatter and body from markdown content.

        Args:
            content: The markdown file content

        Returns:
            Tuple of (frontmatter_dict, body_text)
        """
        if not content.startswith("---"):
            return {}, content

        end_index = content.find("\n---\n", 3)
        if end_index == -1:
            return {}, content

        frontmatter_text = content[3:end_index]
        body_text = content[end_index + 5:]

        try:
            frontmatter = yaml.safe_load(frontmatter_text) or {}
        except yaml.YAMLError:
            frontmatter = {}

        return frontmatter, body_text.strip()

    @staticmethod
    def _extract_sections(body_text: str) -> dict:
        """Extract sections from markdown body by heading level 2.

        Args:
            body_text: The markdown body content

        Returns:
            Dictionary mapping section names to their content
        """
        sections = {}

        pattern = r"^## (.+?)$"
        lines = body_text.split("\n")

        current_section = None
        current_content = []

        for line in lines:
            match = re.match(pattern, line)
            if match:
                if current_section is not None:
                    sections[current_section] = "\n".join(current_content).strip()

                current_section = match.group(1).strip()
                current_content = []
            elif current_section is not None:
                current_content.append(line)

        if current_section is not None:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _get_drift_status(self, capability_id: str, frontmatter: dict) -> str:
        """Get the drift status from frontmatter or index.

        Args:
            capability_id: The capability identifier
            frontmatter: The parsed frontmatter dictionary

        Returns:
            Drift status string
        """
        if "drift_status" in frontmatter:
            return frontmatter["drift_status"]
        return "ok"

    def _match_query(self, query: str) -> list[str]:
        """Find capability IDs matching the query through lexical matching.

        Uses exact ID matches and fuzzy matching on query terms against
        capability IDs.

        Args:
            query: User query string

        Returns:
            List of matched capability IDs
        """
        query_lower = query.lower()
        matched_ids = []

        index = self._load_index()

        for capability_id in self.capabilities_dir.glob("*.md"):
            cap_id = capability_id.stem

            if cap_id in query_lower:
                matched_ids.append(cap_id)
                continue

            query_terms = query_lower.split()
            for term in query_terms:
                if term in cap_id.lower():
                    matched_ids.append(cap_id)
                    break

        if not matched_ids:
            for module_id in index.get("modules", {}):
                if module_id in query_lower:
                    matched_ids.append(module_id)
                    continue

                query_terms = query_lower.split()
                for term in query_terms:
                    if term in module_id.lower():
                        matched_ids.append(module_id)
                        break

        return list(dict.fromkeys(matched_ids))

    def get_context(self, query: str) -> WikiContext:
        """Retrieve wiki context for a user query.

        Performs lexical matching against capability and module IDs,
        loads full markdown content, parses frontmatter and sections,
        and returns structured WikiContext with WikiItem objects.

        Args:
            query: User query string

        Returns:
            WikiContext containing matched WikiItem objects
        """
        context = WikiContext()
        matched_ids = self._match_query(query)

        for item_id in matched_ids:
            capability_file = self.capabilities_dir / f"{item_id}.md"

            if capability_file.exists():
                frontmatter, body_sections = self._load_capability_file(item_id)

                drift_status = self._get_drift_status(item_id, frontmatter)

                wiki_item = WikiItem(
                    item_type="capability",
                    item_id=item_id,
                    drift_status=drift_status,
                    confidence=1.0,
                    frontmatter=frontmatter,
                    body_sections=body_sections,
                )
                context.items.append(wiki_item)
            else:
                index = self._load_index()
                if item_id in index.get("modules", {}):
                    module_data = index["modules"][item_id]
                    wiki_item = WikiItem(
                        item_type="module",
                        item_id=item_id,
                        drift_status=module_data.get("wiki_status", "missing"),
                        confidence=1.0,
                        frontmatter={
                            "module_id": item_id,
                            "code_paths": module_data.get("code_paths", []),
                            "wiki_status": module_data.get("wiki_status", "missing"),
                        },
                        body_sections={},
                    )
                    context.items.append(wiki_item)

        return context
