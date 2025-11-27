#!/usr/bin/env python3
"""
Documentation Catalog - RTFM Before Investigation

Maintains a catalog of all documentation KLoROS has read, preventing:
- Re-reading the same docs
- Investigating already-documented behavior
- Wasting cycles on RTFM-solvable problems

Tracks:
- Which docs have been read
- When they were read
- Key information extracted
- What questions each doc answers

Governance:
- Tool-Integrity: Read-only doc access, safe cataloging
- D-REAM-Allowed-Stack: File I/O, JSON, basic NLP
- Autonomy Level 2: Suggest docs to read, don't auto-execute
"""

import os
import re
import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class DocumentRecord:
    """Record of a documentation file that has been read."""
    path: str
    title: str
    summary: str  # Brief summary of what this doc covers
    keywords: List[str]  # Extracted keywords
    answers_questions: List[str]  # What questions this doc answers
    content_hash: str  # SHA256 of content
    first_read: str
    last_read: str
    read_count: int = 1

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class DocumentCatalog:
    """Catalog of all documentation read by KLoROS."""
    documents: Dict[str, DocumentRecord] = field(default_factory=dict)
    catalog_path: Path = field(default_factory=lambda: Path("/home/kloros/.kloros/documentation_catalog.json"))

    def __post_init__(self):
        """Load existing catalog."""
        self.load()

    def load(self) -> None:
        """Load catalog from disk."""
        if self.catalog_path.exists():
            try:
                data = json.loads(self.catalog_path.read_text())
                for path, doc_data in data.get("documents", {}).items():
                    self.documents[path] = DocumentRecord(**doc_data)
                logger.info(f"[doc_catalog] Loaded {len(self.documents)} documents from catalog")
            except Exception as e:
                logger.warning(f"[doc_catalog] Failed to load catalog: {e}")

    def save(self) -> None:
        """Save catalog to disk."""
        try:
            data = {
                "documents": {path: doc.to_dict() for path, doc in self.documents.items()},
                "last_updated": datetime.now().isoformat()
            }
            self.catalog_path.write_text(json.dumps(data, indent=2))
            logger.debug(f"[doc_catalog] Saved {len(self.documents)} documents to catalog")
        except Exception as e:
            logger.error(f"[doc_catalog] Failed to save catalog: {e}")

    def has_read(self, doc_path: str) -> bool:
        """Check if a document has been read."""
        return doc_path in self.documents

    def get_content_hash(self, content: str) -> str:
        """Calculate SHA256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()

    def has_changed(self, doc_path: str, content: str) -> bool:
        """Check if a document's content has changed since last read."""
        if doc_path not in self.documents:
            return True
        current_hash = self.get_content_hash(content)
        return current_hash != self.documents[doc_path].content_hash

    def extract_keywords(self, content: str, title: str) -> List[str]:
        """
        Extract keywords from document content.

        Simple keyword extraction:
        - Words in title
        - Capitalized technical terms
        - Service names (xxx.service)
        - Common technical keywords
        """
        keywords = set()

        # Add title words
        keywords.update(re.findall(r'\b[A-Z][a-z]+\b', title))

        # Extract service names
        keywords.update(re.findall(r'\b\w+\.service\b', content))

        # Extract capitalized technical terms (2+ words)
        keywords.update(re.findall(r'\b[A-Z][A-Z]+\b', content))

        # Extract header words (lines starting with #)
        headers = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
        for header in headers:
            keywords.update(re.findall(r'\b[A-Za-z]{4,}\b', header))

        # Common technical keywords
        tech_patterns = [
            r'\b(Observer|Orchestrator|D-REAM|PHASE|SPICA|ASTRAEA)\b',
            r'\b(daemon|service|process|thread|worker)\b',
            r'\b(integration|architecture|design|implementation)\b',
        ]
        for pattern in tech_patterns:
            keywords.update(re.findall(pattern, content, re.IGNORECASE))

        return sorted(list(keywords))[:20]  # Top 20 keywords

    def extract_answers(self, content: str) -> List[str]:
        """
        Extract what questions this document answers.

        Looks for:
        - FAQ sections
        - "Why..." questions
        - "What is..." explanations
        - Problem/solution pairs
        """
        answers = []

        # Find FAQ sections
        faq_section = re.search(r'#+\s*FAQ.*?\n(.*?)(?=\n#+|\Z)', content, re.DOTALL | re.IGNORECASE)
        if faq_section:
            questions = re.findall(r'\*\*Q:\s*(.+?)\*\*', faq_section.group(1))
            answers.extend(questions[:5])

        # Find question headers
        question_headers = re.findall(r'^#+\s+(Why|What|How|When)\s+(.+?)$', content, re.MULTILINE | re.IGNORECASE)
        answers.extend([f"{q[0]} {q[1]}" for q in question_headers[:5]])

        # Find problem statements
        problems = re.findall(r'\*\*Problem:\*\*\s*(.+?)(?=\n|$)', content)
        answers.extend([f"Problem: {p}" for p in problems[:3]])

        return answers[:10]  # Top 10 questions

    def record_read(self, doc_path: str, content: str, force: bool = False) -> Optional[DocumentRecord]:
        """
        Record that a document has been read.

        Args:
            doc_path: Path to the document
            content: Document content
            force: Force re-reading even if already read

        Returns:
            DocumentRecord if newly read or updated, None if skipped
        """
        path_str = str(doc_path)

        # Check if already read and unchanged
        if not force and path_str in self.documents:
            if not self.has_changed(path_str, content):
                # Just update read count and timestamp
                self.documents[path_str].read_count += 1
                self.documents[path_str].last_read = datetime.now().isoformat()
                self.save()
                logger.debug(f"[doc_catalog] Document {doc_path} already read (unchanged)")
                return None

        # Extract metadata
        title = self._extract_title(content, doc_path)
        summary = self._extract_summary(content)
        keywords = self.extract_keywords(content, title)
        answers = self.extract_answers(content)
        content_hash = self.get_content_hash(content)

        now = datetime.now().isoformat()

        # Create or update record
        if path_str in self.documents:
            # Update existing record
            record = self.documents[path_str]
            record.content_hash = content_hash
            record.summary = summary
            record.keywords = keywords
            record.answers_questions = answers
            record.last_read = now
            record.read_count += 1
            logger.info(f"[doc_catalog] Updated record for {doc_path} (changed)")
        else:
            # Create new record
            record = DocumentRecord(
                path=path_str,
                title=title,
                summary=summary,
                keywords=keywords,
                answers_questions=answers,
                content_hash=content_hash,
                first_read=now,
                last_read=now
            )
            self.documents[path_str] = record
            logger.info(f"[doc_catalog] Catalogued new document: {title}")

        self.save()
        return record

    def _extract_title(self, content: str, path: Path) -> str:
        """Extract title from document."""
        # Try to find markdown title (# Title)
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()

        # Fall back to filename
        return path.stem.replace('_', ' ').replace('-', ' ').title()

    def _extract_summary(self, content: str, max_length: int = 200) -> str:
        """Extract summary from document."""
        # Look for summary section
        summary_match = re.search(
            r'#+\s*(Summary|Overview|Description).*?\n(.*?)(?=\n#+|\Z)',
            content,
            re.DOTALL | re.IGNORECASE
        )
        if summary_match:
            summary = summary_match.group(2).strip()
            # Clean up markdown
            summary = re.sub(r'\*\*(.+?)\*\*', r'\1', summary)
            summary = re.sub(r'\n+', ' ', summary)
            if len(summary) <= max_length:
                return summary
            return summary[:max_length] + "..."

        # Fall back to first paragraph
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip() and not p.strip().startswith('#')]
        if paragraphs:
            first_para = paragraphs[0]
            if len(first_para) <= max_length:
                return first_para
            return first_para[:max_length] + "..."

        return "No summary available"

    def search_docs(self, query: str, top_n: int = 5) -> List[DocumentRecord]:
        """
        Search catalog for relevant documents.

        Args:
            query: Search query (keywords or question)
            top_n: Number of results to return

        Returns:
            List of DocumentRecords sorted by relevance
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\b\w+\b', query_lower))

        # Score each document
        scores = []
        for doc in self.documents.values():
            score = 0

            # Title match (highest weight)
            if query_lower in doc.title.lower():
                score += 10

            # Keyword matches
            for keyword in doc.keywords:
                if keyword.lower() in query_lower:
                    score += 5

            # Word overlap
            doc_words = set(re.findall(r'\b\w+\b', doc.title.lower() + ' ' + ' '.join(doc.keywords).lower()))
            overlap = len(query_words & doc_words)
            score += overlap * 2

            # Check if doc answers similar questions
            for answer in doc.answers_questions:
                if any(word in answer.lower() for word in query_words):
                    score += 3

            if score > 0:
                scores.append((score, doc))

        # Sort by score and return top N
        scores.sort(reverse=True, key=lambda x: x[0])
        return [doc for score, doc in scores[:top_n]]

    def suggest_docs_for_investigation(self, investigation_query: str) -> List[Dict]:
        """
        Suggest relevant docs before starting investigation.

        Args:
            investigation_query: The question being investigated

        Returns:
            List of suggestions with doc path, title, relevance
        """
        docs = self.search_docs(investigation_query, top_n=5)

        suggestions = []
        for doc in docs:
            suggestions.append({
                "path": doc.path,
                "title": doc.title,
                "summary": doc.summary,
                "relevance": "high" if len(suggestions) == 0 else "medium",
                "recommendation": f"Read {doc.title} - may answer your question"
            })

        return suggestions

    def get_unread_docs(self, docs_dir: Path = Path("/home/kloros/docs")) -> List[Path]:
        """
        Find documentation files that haven't been read yet.

        Args:
            docs_dir: Directory to scan for docs

        Returns:
            List of unread document paths
        """
        unread = []

        if not docs_dir.exists():
            return unread

        for md_file in docs_dir.rglob("*.md"):
            if str(md_file) not in self.documents:
                unread.append(md_file)

        return sorted(unread)

    def stats(self) -> Dict:
        """Get catalog statistics."""
        return {
            "total_documents": len(self.documents),
            "total_reads": sum(doc.read_count for doc in self.documents.values()),
            "unique_keywords": len(set(kw for doc in self.documents.values() for kw in doc.keywords)),
            "most_read": sorted(
                [(doc.title, doc.read_count) for doc in self.documents.values()],
                key=lambda x: x[1],
                reverse=True
            )[:5]
        }


def rtfm_before_investigation(investigation_query: str) -> Dict:
    """
    Check documentation before starting investigation.

    Args:
        investigation_query: The question to investigate

    Returns:
        Dict with suggested docs and whether to proceed with investigation
    """
    catalog = DocumentCatalog()
    suggestions = catalog.suggest_docs_for_investigation(investigation_query)

    if suggestions:
        logger.info(f"[doc_catalog] Found {len(suggestions)} relevant docs for: {investigation_query}")
        return {
            "should_read_docs_first": True,
            "suggested_docs": suggestions,
            "message": f"Found {len(suggestions)} relevant documents. Read these before investigating."
        }
    else:
        logger.info(f"[doc_catalog] No relevant docs found for: {investigation_query}")
        return {
            "should_read_docs_first": False,
            "suggested_docs": [],
            "message": "No relevant documentation found. Proceed with investigation."
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test catalog
    catalog = DocumentCatalog()

    # Test search
    query = "kloros-orchestrator service not running"
    print(f"\nSearching for: {query}")
    suggestions = catalog.suggest_docs_for_investigation(query)

    print(f"\nFound {len(suggestions)} suggestions:")
    for sug in suggestions:
        print(f"  - {sug['title']}: {sug['summary'][:80]}...")

    # Show stats
    print(f"\nCatalog stats:")
    stats = catalog.stats()
    print(f"  Total docs: {stats['total_documents']}")
    print(f"  Total reads: {stats['total_reads']}")
    print(f"  Unique keywords: {stats['unique_keywords']}")
