#!/usr/bin/env python3
"""
Documentation Learning - Semantic Memory Integration

Stores documentation facts as semantic memories so KLoROS can:
- Recall learnings without re-reading docs
- Answer questions from remembered knowledge
- Cite sources for her knowledge
- Build understanding over time

When a doc is read, extracts:
- Key facts and concepts
- Answers to common questions
- Configuration details
- Component relationships
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DocLearner:
    """Commits documentation learnings to semantic memory."""

    def __init__(self):
        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from kloros_memory.logger import MemoryLogger
            from kloros_memory.storage import EventType
            
            self.memory = MemoryLogger()
            self.EventType = EventType
            self.available = True
            logger.info("[doc_learner] ✓ Memory system available")
        except Exception as e:
            logger.warning(f"[doc_learner] Memory system not available: {e}")
            self.available = False

    def extract_facts(self, content: str, doc_path: str, doc_title: str) -> List[Dict]:
        """
        Extract learnable facts from documentation.

        Supports multiple formats: Markdown, YAML, TOML, JSON, TXT

        Returns list of facts, each with:
        - fact: The key learning
        - context: Supporting details
        - category: Type of knowledge (config, architecture, process, etc.)
        """
        facts = []

        # Determine format from file extension
        file_ext = Path(doc_path).suffix.lower()

        if file_ext in ['.yaml', '.yml']:
            facts = self._extract_from_yaml(content, doc_path, doc_title)
        elif file_ext == '.toml':
            facts = self._extract_from_toml(content, doc_path, doc_title)
        elif file_ext == '.json':
            facts = self._extract_from_json(content, doc_path, doc_title)
        elif file_ext == '.txt':
            facts = self._extract_from_text(content, doc_path, doc_title)
        else:  # .md or unknown - treat as markdown
            facts = self._extract_from_markdown(content, doc_path, doc_title)

        return facts

    def _extract_from_markdown(self, content: str, doc_path: str, doc_title: str) -> List[Dict]:
        """Extract facts from markdown documentation."""
        facts = []

        # Split into sections (markdown headings)
        sections = self._split_by_headings(content)

        for heading, text in sections:
            if not text.strip():
                continue

            # Extract different types of facts
            category = self._categorize_section(heading, text)

            # For each meaningful paragraph, create a fact
            paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 50]

            for para in paragraphs[:5]:  # Limit to avoid spam
                # Skip code blocks and lists
                if para.startswith('```') or para.startswith('-') or para.startswith('*'):
                    continue

                facts.append({
                    'fact': para[:500],  # First 500 chars
                    'context': f"{doc_title} → {heading}",
                    'category': category,
                    'doc_path': doc_path,
                    'section': heading
                })

        return facts

    def _extract_from_yaml(self, content: str, doc_path: str, doc_title: str) -> List[Dict]:
        """Extract facts from YAML configuration files."""
        facts = []

        try:
            import yaml
            data = yaml.safe_load(content)

            if not isinstance(data, dict):
                return facts

            # Extract key-value knowledge from YAML
            for key, value in data.items():
                if isinstance(value, dict):
                    # Nested structure - extract description/info
                    for subkey, subvalue in value.items():
                        if subkey in ['description', 'enabled', 'module', 'url', 'port']:
                            fact_text = f"{key}.{subkey} = {subvalue}"
                            facts.append({
                                'fact': fact_text,
                                'context': f"{doc_title} → YAML config",
                                'category': 'configuration',
                                'doc_path': doc_path,
                                'section': key
                            })
                elif isinstance(value, (str, int, float, bool)):
                    # Simple value
                    fact_text = f"{key} = {value}"
                    facts.append({
                        'fact': fact_text,
                        'context': f"{doc_title} → YAML config",
                        'category': 'configuration',
                        'doc_path': doc_path,
                        'section': 'root'
                    })
        except Exception as e:
            logger.warning(f"[doc_learner] Failed to parse YAML: {e}")

        return facts[:20]  # Limit YAML facts

    def _extract_from_toml(self, content: str, doc_path: str, doc_title: str) -> List[Dict]:
        """Extract facts from TOML configuration files."""
        facts = []

        try:
            import tomllib
            data = tomllib.loads(content)

            # Extract key-value knowledge from TOML sections
            for section, values in data.items():
                if isinstance(values, dict):
                    for key, value in values.items():
                        if isinstance(value, dict):
                            # Nested dict - extract description
                            desc = value.get('description', value.get('model', str(value)[:100]))
                            fact_text = f"{section}.{key} = {desc}"
                        else:
                            fact_text = f"{section}.{key} = {value}"

                        facts.append({
                            'fact': fact_text,
                            'context': f"{doc_title} → TOML [{section}]",
                            'category': 'configuration',
                            'doc_path': doc_path,
                            'section': section
                        })
                else:
                    fact_text = f"{section} = {values}"
                    facts.append({
                        'fact': fact_text,
                        'context': f"{doc_title} → TOML config",
                        'category': 'configuration',
                        'doc_path': doc_path,
                        'section': 'root'
                    })
        except Exception as e:
            logger.warning(f"[doc_learner] Failed to parse TOML: {e}")

        return facts[:20]  # Limit TOML facts

    def _extract_from_json(self, content: str, doc_path: str, doc_title: str) -> List[Dict]:
        """Extract facts from JSON files."""
        facts = []

        try:
            import json as json_module
            data = json_module.loads(content)

            # Extract schema or key information
            if isinstance(data, dict):
                for key, value in list(data.items())[:15]:  # Limit to first 15 keys
                    if isinstance(value, dict):
                        fact_text = f"{key}: {json_module.dumps(value, indent=None)[:200]}"
                    else:
                        fact_text = f"{key} = {value}"

                    facts.append({
                        'fact': fact_text,
                        'context': f"{doc_title} → JSON data",
                        'category': 'configuration',
                        'doc_path': doc_path,
                        'section': key
                    })
        except Exception as e:
            logger.warning(f"[doc_learner] Failed to parse JSON: {e}")

        return facts

    def _extract_from_text(self, content: str, doc_path: str, doc_title: str) -> List[Dict]:
        """Extract facts from plain text files."""
        facts = []

        # Split by blank lines (paragraphs)
        paragraphs = [p.strip() for p in content.split('\n\n') if len(p.strip()) > 50]

        for para in paragraphs[:10]:  # Limit to 10 paragraphs
            facts.append({
                'fact': para[:500],
                'context': f"{doc_title} → Text content",
                'category': 'general',
                'doc_path': doc_path,
                'section': 'main'
            })

        return facts

    def _split_by_headings(self, content: str) -> List[tuple]:
        """Split content by markdown headings."""
        import re
        
        sections = []
        current_heading = "Introduction"
        current_text = []
        
        for line in content.split('\n'):
            # Check if line is a heading
            heading_match = re.match(r'^#{1,4}\s+(.+)', line)
            if heading_match:
                # Save previous section
                if current_text:
                    sections.append((current_heading, '\n'.join(current_text)))
                current_heading = heading_match.group(1)
                current_text = []
            else:
                current_text.append(line)
        
        # Save last section
        if current_text:
            sections.append((current_heading, '\n'.join(current_text)))
        
        return sections

    def _categorize_section(self, heading: str, text: str) -> str:
        """Categorize type of knowledge."""
        heading_lower = heading.lower()
        text_lower = text.lower()
        
        if any(kw in heading_lower for kw in ['config', 'setting', 'parameter']):
            return 'configuration'
        elif any(kw in heading_lower for kw in ['architecture', 'design', 'structure']):
            return 'architecture'
        elif any(kw in heading_lower for kw in ['how', 'process', 'workflow']):
            return 'process'
        elif any(kw in heading_lower for kw in ['why', 'reason', 'rationale']):
            return 'rationale'
        elif '.service' in text_lower or 'systemd' in text_lower:
            return 'service_management'
        elif 'deprecated' in text_lower or 'replaced' in text_lower:
            return 'evolution'
        else:
            return 'general'

    def commit_learning(self, doc_path: str, content: str, doc_title: str) -> int:
        """
        Extract facts from doc and commit to memory.
        
        Returns:
            Number of facts committed
        """
        if not self.available:
            logger.warning("[doc_learner] Memory not available, skipping learning")
            return 0
        
        facts = self.extract_facts(content, doc_path, doc_title)
        
        if not facts:
            logger.debug(f"[doc_learner] No facts extracted from {doc_path}")
            return 0
        
        # Commit each fact as a memory event
        committed = 0
        for fact in facts:
            try:
                self.memory.log_event(
                    event_type=self.EventType.DOCUMENTATION_LEARNED,
                    content=fact['fact'],
                    metadata={
                        'doc_path': fact['doc_path'],
                        'doc_title': doc_title,
                        'section': fact['section'],
                        'category': fact['category'],
                        'context': fact['context'],
                        'learned_at': datetime.now().isoformat()
                    }
                )
                committed += 1
            except Exception as e:
                logger.warning(f"[doc_learner] Failed to commit fact: {e}")

        # Flush to ensure learnings are persisted immediately
        if committed > 0:
            try:
                self.memory._flush_cache()
                logger.info(f"[doc_learner] ✓ Committed {committed} learnings from {doc_title}")
            except Exception as e:
                logger.warning(f"[doc_learner] Failed to flush cache: {e}")

        return committed


def learn_from_document(doc_path: Path, content: str, doc_title: str) -> int:
    """
    Main entry point: Extract and commit learnings from a document.
    
    Args:
        doc_path: Path to document
        content: Full document content
        doc_title: Document title
    
    Returns:
        Number of facts committed to memory
    """
    learner = DocLearner()
    return learner.commit_learning(str(doc_path), content, doc_title)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test with a sample doc
    sample_doc = """
# Phase 4: Orchestrator Timer Disablement

## Why This Was Done

The orchestrator timer was intentionally disabled to reduce power consumption
during idle periods. This is part of the power optimization strategy.

## Configuration

To check the status:
```bash
systemctl status kloros-orchestrator.service
```

The service is designed to be triggered on-demand rather than running continuously.
"""
    
    learner = DocLearner()
    facts = learner.extract_facts(sample_doc, "/home/kloros/docs/test.md", "Test Doc")
    print(f"Extracted {len(facts)} facts:")
    for fact in facts:
        print(f"  [{fact['category']}] {fact['fact'][:80]}...")
