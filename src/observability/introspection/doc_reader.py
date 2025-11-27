#!/usr/bin/env python3
"""
Document Reader - Automatic Documentation Cataloging

Reads documentation files and adds them to the catalog.
Can be run:
- Manually for specific docs
- Automatically before investigations
- As a batch job to catalog all docs

Governance:
- Tool-Integrity: Read-only access to docs
- D-REAM-Allowed-Stack: File I/O only
- Safe: No code execution, just reading
"""

import logging
from pathlib import Path
from typing import List, Optional
from src.observability.introspection.documentation_catalog import DocumentCatalog, rtfm_before_investigation

logger = logging.getLogger(__name__)


class DocReader:
    """Reads and catalogs documentation files."""

    def __init__(self):
        self.catalog = DocumentCatalog()
        self.docs_dir = Path("/home/kloros/docs")
        self.src_docs = Path("/home/kloros/src")

    def read_doc(self, doc_path: Path, force: bool = False) -> bool:
        """
        Read a single document and catalog it.

        Also commits learnings to semantic memory for recall without re-reading.

        Args:
            doc_path: Path to document
            force: Force re-reading even if already cataloged

        Returns:
            True if read successfully, False otherwise
        """
        try:
            if not doc_path.exists():
                logger.warning(f"[doc_reader] Document not found: {doc_path}")
                return False

            content = doc_path.read_text()
            record = self.catalog.record_read(doc_path, content, force=force)

            if record:
                logger.info(f"[doc_reader] ✓ Read and cataloged: {record.title}")
                logger.info(f"[doc_reader]   Keywords: {', '.join(record.keywords[:5])}")

                # Commit learnings to memory (new or updated docs only)
                try:
                    from src.observability.introspection.doc_learning import learn_from_document
                    facts_count = learn_from_document(doc_path, content, record.title)
                    if facts_count > 0:
                        logger.info(f"[doc_reader]   💾 Committed {facts_count} learnings to memory")
                except Exception as e:
                    logger.warning(f"[doc_reader] Failed to commit learnings: {e}")

                return True
            else:
                logger.debug(f"[doc_reader] Document already cataloged (unchanged): {doc_path}")
                return True

        except Exception as e:
            logger.error(f"[doc_reader] Failed to read {doc_path}: {e}")
            return False

    def catalog_all_docs(self, force: bool = False, file_types: Optional[List[str]] = None) -> int:
        """
        Catalog all documentation files in known locations.

        Args:
            force: Force re-reading all docs
            file_types: List of file extensions to include (default: md, txt, yaml, yml, toml, json)

        Returns:
            Number of docs cataloged
        """
        if file_types is None:
            file_types = ['.md', '.txt', '.yaml', '.yml', '.toml', '.json']

        cataloged = 0

        # Scan /home/kloros/docs
        if self.docs_dir.exists():
            for doc_file in self.docs_dir.rglob("*"):
                if doc_file.is_file() and doc_file.suffix in file_types:
                    if self.read_doc(doc_file, force=force):
                        cataloged += 1

        # Scan /home/kloros/src for README.md files
        if self.src_docs.exists():
            for md_file in self.src_docs.rglob("README.md"):
                if self.read_doc(md_file, force=force):
                    cataloged += 1

        # Scan /home/kloros/config for config files
        config_dir = Path("/home/kloros/config")
        if config_dir.exists():
            for config_file in config_dir.glob("*"):
                if config_file.is_file() and config_file.suffix in ['.yaml', '.yml', '.toml', '.json']:
                    if self.read_doc(config_file, force=force):
                        cataloged += 1

        logger.info(f"[doc_reader] Cataloged {cataloged} documents")
        return cataloged

    def suggest_reading_for_query(self, query: str) -> List[str]:
        """
        Suggest docs to read for a given query.

        Args:
            query: Investigation query or question

        Returns:
            List of doc paths to read
        """
        suggestions = self.catalog.suggest_docs_for_investigation(query)

        # Return paths of suggested docs
        return [sug["path"] for sug in suggestions]

    def read_suggested_docs(self, query: str, max_docs: int = 3) -> List[str]:
        """
        Read suggested docs for a query and return their content.

        Args:
            query: Investigation query
            max_docs: Maximum number of docs to read

        Returns:
            List of doc titles that were read
        """
        suggested_paths = self.suggest_reading_for_query(query)
        read_titles = []

        for path_str in suggested_paths[:max_docs]:
            path = Path(path_str)
            if self.read_doc(path):
                # Get title from catalog
                if path_str in self.catalog.documents:
                    read_titles.append(self.catalog.documents[path_str].title)

        return read_titles


def rtfm_check(investigation_query: str) -> dict:
    """
    Perform RTFM check before investigation.

    This is the main entry point for investigation handlers.

    Args:
        investigation_query: The question being investigated

    Returns:
        Dict with:
        - should_read_docs_first: bool
        - suggested_docs: list of {path, title, summary}
        - relevant_content: dict of doc_path -> extracted relevant sections
    """
    result = rtfm_before_investigation(investigation_query)

    # If docs are suggested, extract relevant content
    if result["should_read_docs_first"] and result["suggested_docs"]:
        relevant_content = {}

        for doc_info in result["suggested_docs"]:
            doc_path = Path(doc_info["path"])
            if doc_path.exists():
                try:
                    content = doc_path.read_text()
                    # Extract most relevant sections (TODO: improve with better extraction)
                    relevant_content[str(doc_path)] = {
                        "title": doc_info["title"],
                        "summary": doc_info["summary"],
                        "full_content": content[:2000]  # First 2000 chars
                    }
                except Exception as e:
                    logger.warning(f"[rtfm_check] Could not read {doc_path}: {e}")

        result["relevant_content"] = relevant_content

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    reader = DocReader()

    # Catalog all docs
    print("Cataloging all documentation...")
    count = reader.catalog_all_docs()
    print(f"Cataloged {count} documents")

    # Test RTFM check
    query = "kloros-orchestrator service not running"
    print(f"\n=== RTFM Check for: {query} ===")
    result = rtfm_check(query)

    print(f"\nShould read docs first? {result['should_read_docs_first']}")
    print(f"Message: {result['message']}")

    if result.get('suggested_docs'):
        print(f"\nSuggested docs ({len(result['suggested_docs'])}):")
        for doc in result['suggested_docs']:
            print(f"  - {doc['title']}")
            print(f"    {doc['summary'][:100]}...")

    # Show catalog stats
    print(f"\n=== Catalog Stats ===")
    stats = reader.catalog.stats()
    print(f"Total docs: {stats['total_documents']}")
    print(f"Total reads: {stats['total_reads']}")
    print(f"Most read:")
    for title, count in stats['most_read']:
        print(f"  - {title}: {count} reads")
