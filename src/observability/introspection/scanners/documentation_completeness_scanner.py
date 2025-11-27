#!/usr/bin/env python3
"""
Documentation Completeness Scanner

Compares formal documentation against actual component capabilities
to identify gaps and staleness.

Purpose:
Ensures documentation keeps pace with implementation by detecting:
- Undocumented components (no docs exist at all)
- Underdocumented components (partial/thin coverage)
- Stale documentation (docs older than code changes)
"""

import logging
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, NamedTuple, Set, Tuple
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


class ScannerMetadata(NamedTuple):
    name: str
    description: str
    interval_seconds: int
    priority: int


class DocumentationCompletenessScanner:
    """Detects documentation gaps by comparing docs against component knowledge."""

    def __init__(self, knowledge_db_path: str = '/home/kloros/data/knowledge.db',
                 docs_path: str = '/home/kloros/docs'):
        self.knowledge_db_path = knowledge_db_path
        self.docs_path = Path(docs_path)
        self.available = True
        self.last_scan_time = None
        self.cached_results = None

        try:
            if not self.docs_path.exists():
                logger.warning(f"[doc_completeness] Docs directory not found: {self.docs_path}")
                self.available = False

            if not Path(knowledge_db_path).exists():
                logger.warning(f"[doc_completeness] Knowledge DB not found: {knowledge_db_path}")
                self.available = False

        except Exception as e:
            logger.warning(f"[doc_completeness] Initialization failed: {e}")
            self.available = False

    def get_metadata(self) -> ScannerMetadata:
        return ScannerMetadata(
            name="documentation_completeness_scanner",
            description="Compares documentation against component knowledge to identify gaps and staleness",
            interval_seconds=1800,
            priority=1
        )

    def scan(self) -> List:
        """
        Daemon-compatible interface - returns empty list per design.
        Primary method is scan_documentation().
        """
        return []

    def scan_documentation(self, lookback_days: int = 30) -> Dict:
        """
        Analyze documentation completeness and identify gaps.

        Args:
            lookback_days: How far back to check for stale documentation

        Returns:
            {
                'undocumented': [...],
                'underdocumented': [...],
                'stale_documentation': [...],
                'coverage_summary': {...},
                'scan_metadata': {...}
            }
        """
        if not self.available:
            logger.warning("[doc_completeness] Scanner not available")
            return self._empty_results(lookback_days)

        now = datetime.now()

        if (self.last_scan_time and
            self.cached_results and
            (now - self.last_scan_time).total_seconds() < 1800):
            logger.debug("[doc_completeness] Returning cached results (within 30-minute window)")
            return self.cached_results

        try:
            components = self._load_component_knowledge()
            doc_inventory = self._parse_docs_directory()

            undocumented = self._find_undocumented_components(components, doc_inventory)
            underdocumented = self._find_underdocumented_components(components, doc_inventory)
            stale = self._detect_stale_documentation(components, doc_inventory, lookback_days)
            coverage = self._calculate_coverage(components, doc_inventory)

            results = {
                'undocumented': undocumented,
                'underdocumented': underdocumented,
                'stale_documentation': stale,
                'coverage_summary': {
                    'total_components': len(components),
                    'documented_components': len([c for c in components.values() if c.get('has_docs')]),
                    'coverage_percentage': coverage
                },
                'scan_metadata': {
                    'timestamp': now.isoformat(),
                    'lookback_days': lookback_days,
                    'docs_path': str(self.docs_path),
                    'knowledge_db_path': self.knowledge_db_path
                }
            }

            self.last_scan_time = now
            self.cached_results = results

            return results

        except Exception as e:
            logger.error(f"[doc_completeness] Scan failed: {e}")
            return self._empty_results(lookback_days)

    def _empty_results(self, lookback_days: int) -> Dict:
        """Return empty results structure."""
        return {
            'undocumented': [],
            'underdocumented': [],
            'stale_documentation': [],
            'coverage_summary': {
                'total_components': 0,
                'documented_components': 0,
                'coverage_percentage': 0.0
            },
            'scan_metadata': {
                'timestamp': datetime.now().isoformat(),
                'lookback_days': lookback_days,
                'docs_path': str(self.docs_path),
                'knowledge_db_path': self.knowledge_db_path
            }
        }

    def _load_component_knowledge(self) -> Dict[str, Dict]:
        """
        Load component data from knowledge.db.

        Returns dict of components with metadata.
        """
        components = {}

        try:
            if not Path(self.knowledge_db_path).exists():
                logger.warning(f"[doc_completeness] Knowledge DB not found: {self.knowledge_db_path}")
                return components

            conn = sqlite3.connect(self.knowledge_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT component_id, component_type, file_path,
                       purpose, capabilities, last_studied_at
                FROM component_knowledge
                WHERE study_depth >= 2
            """)

            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                component_id = row['component_id']
                try:
                    capabilities = json.loads(row['capabilities']) if row['capabilities'] else []
                except (json.JSONDecodeError, TypeError):
                    capabilities = []

                components[component_id] = {
                    'component_type': row['component_type'],
                    'file_path': row['file_path'],
                    'purpose': row['purpose'],
                    'capabilities': capabilities,
                    'last_studied_at': row['last_studied_at'],
                    'has_docs': False
                }

        except Exception as e:
            logger.warning(f"[doc_completeness] Failed to load components: {e}")

        return components

    def _parse_docs_directory(self) -> Dict[str, Dict]:
        """
        Parse all markdown files in docs directory.

        Returns dict mapping file paths to content and metadata.
        """
        doc_inventory = {}

        try:
            if not self.docs_path.exists():
                logger.warning(f"[doc_completeness] Docs directory not found: {self.docs_path}")
                return doc_inventory

            for md_file in self.docs_path.rglob('*.md'):
                try:
                    with open(md_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    stat = md_file.stat()
                    doc_inventory[str(md_file)] = {
                        'content': content,
                        'last_modified': datetime.fromtimestamp(stat.st_mtime),
                        'size': stat.st_size,
                        'relative_path': md_file.relative_to(self.docs_path)
                    }

                except Exception as e:
                    logger.debug(f"[doc_completeness] Error reading {md_file}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"[doc_completeness] Failed to parse docs directory: {e}")

        return doc_inventory

    def _find_doc_mentions(self, component_name: str, file_path: str,
                           doc_inventory: Dict[str, Dict]) -> List[str]:
        """
        Find which documentation files mention this component.

        Returns list of doc file paths that mention the component.
        """
        mentioned_in = []

        component_name_lower = component_name.lower()
        file_name_lower = Path(file_path).stem.lower() if file_path else ""

        for doc_path, doc_data in doc_inventory.items():
            content_lower = doc_data['content'].lower()

            if (component_name_lower in content_lower or
                file_name_lower in content_lower):
                mentioned_in.append(doc_path)

        return mentioned_in

    def _extract_documented_capabilities(self, doc_content: str) -> Set[str]:
        """
        Extract capability mentions from documentation.

        Looks for common capability keywords and patterns.
        """
        capabilities = set()

        doc_lower = doc_content.lower()

        keywords = [
            'read', 'write', 'delete', 'create', 'update', 'retrieve',
            'parse', 'validate', 'transform', 'cache', 'store', 'query',
            'search', 'index', 'monitor', 'analyze', 'detect', 'scan',
            'correlate', 'synthesize', 'reason', 'investigate', 'report'
        ]

        for keyword in keywords:
            if keyword in doc_lower:
                capabilities.add(keyword)

        return capabilities

    def _assess_severity(self, component: Dict) -> str:
        """
        Assess severity based on component importance.

        Core components (memory, orchestrator, introspection) are critical.
        """
        component_type = component.get('component_type', '').lower()
        file_path = component.get('file_path', '').lower()

        core_indicators = [
            'memory', 'orchestrator', 'introspection', 'core',
            'agent', 'brain', 'investigator'
        ]

        for indicator in core_indicators:
            if indicator in component_type or indicator in file_path:
                return 'critical'

        return 'error'

    def _find_undocumented_components(self, components: Dict[str, Dict],
                                      doc_inventory: Dict[str, Dict]) -> List[Dict]:
        """Find components with no documentation at all."""
        undocumented = []

        for component_id, component_data in components.items():
            component_name = self._extract_component_name(component_id)
            file_path = component_data.get('file_path', '')

            mentioned_in = self._find_doc_mentions(component_name, file_path, doc_inventory)

            if not mentioned_in:
                undocumented.append({
                    'component': component_id,
                    'type': component_data.get('component_type'),
                    'file_path': file_path,
                    'capabilities': component_data.get('capabilities', []),
                    'severity': self._assess_severity(component_data),
                    'reason': 'No documentation found'
                })
            else:
                component_data['has_docs'] = True

        return undocumented

    def _find_underdocumented_components(self, components: Dict[str, Dict],
                                         doc_inventory: Dict[str, Dict]) -> List[Dict]:
        """Find components with incomplete documentation coverage."""
        underdocumented = []

        for component_id, component_data in components.items():
            actual_caps = set(component_data.get('capabilities', []))

            if not actual_caps:
                continue

            component_name = self._extract_component_name(component_id)
            file_path = component_data.get('file_path', '')

            mentioned_in = self._find_doc_mentions(component_name, file_path, doc_inventory)

            if mentioned_in:
                combined_doc_content = ' '.join(
                    doc_inventory[doc_path]['content']
                    for doc_path in mentioned_in
                )

                documented_caps = self._extract_documented_capabilities(combined_doc_content)

                missing_caps = actual_caps - documented_caps

                if missing_caps:
                    coverage_pct = (len(documented_caps) / len(actual_caps) * 100) if actual_caps else 0

                    underdocumented.append({
                        'component': component_id,
                        'doc_paths': mentioned_in,
                        'coverage_score': coverage_pct / 100.0,
                        'documented_capabilities': sorted(list(documented_caps)),
                        'missing_capabilities': sorted(list(missing_caps)),
                        'severity': 'warning' if coverage_pct >= 30 else 'error'
                    })

        return underdocumented

    def _detect_stale_documentation(self, components: Dict[str, Dict],
                                    doc_inventory: Dict[str, Dict],
                                    lookback_days: int) -> List[Dict]:
        """Find documentation that hasn't been updated since code changed."""
        stale_docs = []

        cutoff_date = datetime.now() - timedelta(days=lookback_days)

        for component_id, component_data in components.items():
            component_name = self._extract_component_name(component_id)
            file_path = component_data.get('file_path', '')
            last_studied = component_data.get('last_studied_at')

            if not last_studied:
                continue

            try:
                if isinstance(last_studied, str):
                    last_studied_dt = datetime.fromisoformat(last_studied)
                else:
                    last_studied_dt = last_studied
            except (ValueError, TypeError):
                continue

            mentioned_in = self._find_doc_mentions(component_name, file_path, doc_inventory)

            for doc_path in mentioned_in:
                doc_data = doc_inventory[doc_path]
                doc_modified = doc_data['last_modified']

                if last_studied_dt > doc_modified:
                    staleness_days = (last_studied_dt - doc_modified).days

                    if staleness_days > 0:
                        if staleness_days > 60:
                            severity = 'error'
                        elif staleness_days > 30:
                            severity = 'warning'
                        else:
                            severity = 'info'

                        stale_docs.append({
                            'component': component_id,
                            'doc_path': doc_path,
                            'doc_modified': doc_modified.isoformat(),
                            'code_modified': last_studied_dt.isoformat(),
                            'staleness_days': staleness_days,
                            'severity': severity
                        })

        return stale_docs

    def _calculate_coverage(self, components: Dict[str, Dict],
                            doc_inventory: Dict[str, Dict]) -> float:
        """Calculate overall documentation coverage percentage."""
        if not components:
            return 0.0

        documented_count = 0

        for component_data in components.values():
            if component_data.get('has_docs'):
                documented_count += 1

        coverage_pct = (documented_count / len(components) * 100) if components else 0
        return min(100.0, max(0.0, coverage_pct))

    def _extract_component_name(self, component_id: str) -> str:
        """
        Extract component name from ID.

        Examples:
        - "module:foo.py" → "foo"
        - "class:MyClass" → "myclass"
        """
        if ':' in component_id:
            return component_id.split(':', 1)[1].lower().split('.')[0]
        return component_id.lower().split('.')[0]

    def format_findings(self, findings: Dict) -> str:
        """Format documentation findings as human-readable report."""
        meta = findings.get('scan_metadata', {})
        coverage = findings.get('coverage_summary', {})

        header = [
            "="*70,
            "DOCUMENTATION COMPLETENESS SCAN REPORT",
            f"Timestamp: {meta.get('timestamp', 'N/A')}",
            f"Lookback: {meta.get('lookback_days', 30)} days",
            f"Documentation Coverage: {coverage.get('coverage_percentage', 0):.1f}% "
            f"({coverage.get('documented_components', 0)}/{coverage.get('total_components', 0)} components)",
            "="*70
        ]

        if not findings or all(not findings.get(key, []) for key in ['undocumented', 'underdocumented', 'stale_documentation']):
            return '\n'.join(header + ['', 'All documentation appears complete!'])

        report = []

        undocumented = findings.get('undocumented', [])
        if undocumented:
            report.append(f"\nUNDOCUMENTED COMPONENTS ({len(undocumented)} found)")
            critical = [c for c in undocumented if c['severity'] == 'critical']
            if critical:
                report.append(f"  CRITICAL ({len(critical)}):")
                for comp in critical[:5]:
                    report.append(f"    - {comp['component']}")
                    report.append(f"      Capabilities: {', '.join(comp['capabilities'][:3])}")

            errors = [c for c in undocumented if c['severity'] == 'error']
            if errors:
                report.append(f"  ERROR ({len(errors)}):")
                for comp in errors[:5]:
                    report.append(f"    - {comp['component']}")

        underdocumented = findings.get('underdocumented', [])
        if underdocumented:
            report.append(f"\nUNDERDOCUMENTED COMPONENTS ({len(underdocumented)} found)")
            for comp in underdocumented[:5]:
                coverage = comp.get('coverage_score', 0) * 100
                report.append(f"  {comp['component']}")
                report.append(f"    Coverage: {coverage:.0f}%")
                report.append(f"    Missing: {', '.join(comp['missing_capabilities'][:3])}")

        stale = findings.get('stale_documentation', [])
        if stale:
            report.append(f"\nSTALE DOCUMENTATION ({len(stale)} found)")
            for doc in stale[:5]:
                report.append(f"  {doc['component']}")
                report.append(f"    Stale by: {doc['staleness_days']} days")
                report.append(f"    Severity: {doc['severity']}")

        return '\n'.join(header + report)


def scan_documentation_standalone(lookback_days: int = 30) -> tuple:
    """CLI entry point: Scan documentation completeness."""
    scanner = DocumentationCompletenessScanner()
    findings = scanner.scan_documentation(lookback_days)
    report = scanner.format_findings(findings)

    return findings, report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    findings, report = scan_documentation_standalone(lookback_days=30)

    print(report)

    if findings:
        print("\n" + "="*70)
        print("DETAILED FINDINGS SUMMARY")
        print("="*70)
        print(f"Undocumented: {len(findings.get('undocumented', []))}")
        print(f"Underdocumented: {len(findings.get('underdocumented', []))}")
        print(f"Stale docs: {len(findings.get('stale_documentation', []))}")
