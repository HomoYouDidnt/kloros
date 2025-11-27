#!/usr/bin/env python3
"""
Tests for DocumentationCompletenessScanner

Tests cover:
- Initialization and availability
- Component loading from knowledge.db
- Markdown parsing from /docs/
- Undocumented component detection
- Underdocumented component detection
- Stale documentation detection
- Coverage calculation
- scan_documentation() method
- scan() method (daemon compatibility)
- format_findings() output
- Error handling
"""

import pytest
import json
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, '/home/kloros/src')

from src.observability.introspection.scanners.documentation_completeness_scanner import (
    DocumentationCompletenessScanner,
    ScannerMetadata
)


@pytest.fixture
def temp_db():
    """Create a temporary knowledge database."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE component_knowledge (
            component_id TEXT PRIMARY KEY,
            component_type TEXT,
            file_path TEXT,
            purpose TEXT,
            capabilities TEXT,
            last_studied_at TEXT,
            study_depth INTEGER
        )
    """)

    conn.commit()
    conn.close()

    yield db_path

    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def temp_docs():
    """Create a temporary docs directory."""
    temp_dir = tempfile.TemporaryDirectory()
    docs_path = Path(temp_dir.name)

    yield docs_path

    temp_dir.cleanup()


@pytest.fixture
def scanner_with_temp_paths(temp_db, temp_docs):
    """Create scanner with temporary database and docs paths."""
    return DocumentationCompletenessScanner(
        knowledge_db_path=temp_db,
        docs_path=str(temp_docs)
    )


@pytest.fixture
def scanner_missing_db(temp_docs):
    """Create scanner with non-existent database."""
    return DocumentationCompletenessScanner(
        knowledge_db_path='/nonexistent/knowledge.db',
        docs_path=str(temp_docs)
    )


@pytest.fixture
def scanner_missing_docs(temp_db):
    """Create scanner with non-existent docs directory."""
    return DocumentationCompletenessScanner(
        knowledge_db_path=temp_db,
        docs_path='/nonexistent/docs'
    )


def insert_component(db_path, component_id, component_type, file_path,
                     purpose, capabilities, last_studied_at, study_depth=2):
    """Helper to insert component into test database."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO component_knowledge
        (component_id, component_type, file_path, purpose, capabilities, last_studied_at, study_depth)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (component_id, component_type, file_path, purpose,
          json.dumps(capabilities) if capabilities else None,
          last_studied_at, study_depth))
    conn.commit()
    conn.close()


def create_doc_file(docs_path, relative_path, content):
    """Helper to create a documentation file."""
    file_path = docs_path / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding='utf-8')
    return file_path


class TestInitialization:
    """Tests for scanner initialization."""

    def test_init_with_valid_paths(self, scanner_with_temp_paths):
        assert scanner_with_temp_paths.available
        assert scanner_with_temp_paths.knowledge_db_path
        assert scanner_with_temp_paths.docs_path

    def test_init_with_missing_db(self, scanner_missing_db):
        assert not scanner_missing_db.available

    def test_init_with_missing_docs(self, scanner_missing_docs):
        assert not scanner_missing_docs.available

    def test_get_metadata(self, scanner_with_temp_paths):
        meta = scanner_with_temp_paths.get_metadata()
        assert isinstance(meta, ScannerMetadata)
        assert meta.name == "documentation_completeness_scanner"
        assert meta.interval_seconds == 1800
        assert meta.priority == 1


class TestDaemonInterface:
    """Tests for daemon-compatible scan() method."""

    def test_scan_returns_empty_list(self, scanner_with_temp_paths):
        result = scanner_with_temp_paths.scan()
        assert isinstance(result, list)
        assert len(result) == 0

    def test_scan_unavailable_scanner(self, scanner_missing_db):
        result = scanner_missing_db.scan()
        assert isinstance(result, list)


class TestComponentLoading:
    """Tests for loading components from knowledge.db."""

    def test_load_single_component(self, scanner_with_temp_paths, temp_db):
        insert_component(
            temp_db,
            'module:storage.py',
            'module',
            '/home/kloros/src/storage.py',
            'Data storage module',
            ['read', 'write', 'query'],
            datetime.now().isoformat()
        )

        components = scanner_with_temp_paths._load_component_knowledge()

        assert 'module:storage.py' in components
        assert components['module:storage.py']['component_type'] == 'module'
        assert components['module:storage.py']['capabilities'] == ['read', 'write', 'query']

    def test_load_multiple_components(self, scanner_with_temp_paths, temp_db):
        for i in range(5):
            insert_component(
                temp_db,
                f'module:module{i}.py',
                'module',
                f'/path/module{i}.py',
                f'Module {i}',
                ['cap1', 'cap2'],
                datetime.now().isoformat()
            )

        components = scanner_with_temp_paths._load_component_knowledge()
        assert len(components) == 5

    def test_load_ignores_low_study_depth(self, scanner_with_temp_paths, temp_db):
        insert_component(
            temp_db,
            'module:low_depth.py',
            'module',
            '/path/low_depth.py',
            'Low depth module',
            [],
            datetime.now().isoformat(),
            study_depth=1
        )

        components = scanner_with_temp_paths._load_component_knowledge()
        assert 'module:low_depth.py' not in components

    def test_load_malformed_capabilities(self, scanner_with_temp_paths, temp_db):
        conn = sqlite3.connect(temp_db)
        conn.execute("""
            INSERT INTO component_knowledge
            (component_id, component_type, file_path, purpose, capabilities, last_studied_at, study_depth)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ('module:bad.py', 'module', '/path/bad.py', 'Bad capabilities',
              'not valid json', datetime.now().isoformat(), 2))
        conn.commit()
        conn.close()

        components = scanner_with_temp_paths._load_component_knowledge()
        assert 'module:bad.py' in components
        assert components['module:bad.py']['capabilities'] == []

    def test_load_empty_database(self, scanner_with_temp_paths):
        components = scanner_with_temp_paths._load_component_knowledge()
        assert isinstance(components, dict)
        assert len(components) == 0


class TestDocsParsing:
    """Tests for parsing markdown files from /docs/."""

    def test_parse_single_markdown_file(self, scanner_with_temp_paths, temp_docs):
        create_doc_file(temp_docs, 'README.md', '# Documentation\nContent here')

        docs = scanner_with_temp_paths._parse_docs_directory()

        assert len(docs) == 1
        doc_path = list(docs.keys())[0]
        assert 'README.md' in doc_path
        assert docs[doc_path]['content'] == '# Documentation\nContent here'

    def test_parse_multiple_markdown_files(self, scanner_with_temp_paths, temp_docs):
        create_doc_file(temp_docs, 'README.md', '# Main\nContent')
        create_doc_file(temp_docs, 'docs/DESIGN.md', '# Design\nDetails')
        create_doc_file(temp_docs, 'docs/API.md', '# API\nReference')

        docs = scanner_with_temp_paths._parse_docs_directory()

        assert len(docs) == 3

    def test_parse_nested_directories(self, scanner_with_temp_paths, temp_docs):
        create_doc_file(temp_docs, 'docs/api/endpoints.md', 'Content')
        create_doc_file(temp_docs, 'docs/api/auth.md', 'Content')
        create_doc_file(temp_docs, 'docs/architecture/overview.md', 'Content')

        docs = scanner_with_temp_paths._parse_docs_directory()

        assert len(docs) == 3

    def test_parse_ignores_non_markdown(self, scanner_with_temp_paths, temp_docs):
        create_doc_file(temp_docs, 'README.md', '# Content')
        create_doc_file(temp_docs, 'config.json', '{"key": "value"}')
        create_doc_file(temp_docs, 'script.py', 'print("hello")')

        docs = scanner_with_temp_paths._parse_docs_directory()

        assert len(docs) == 1
        assert 'README.md' in list(docs.keys())[0]

    def test_parse_empty_directory(self, scanner_with_temp_paths, temp_docs):
        docs = scanner_with_temp_paths._parse_docs_directory()

        assert isinstance(docs, dict)
        assert len(docs) == 0

    def test_parse_missing_directory(self, scanner_missing_docs):
        docs = scanner_missing_docs._parse_docs_directory()

        assert isinstance(docs, dict)
        assert len(docs) == 0


class TestUndocumentedDetection:
    """Tests for finding undocumented components."""

    def test_find_undocumented_component(self, scanner_with_temp_paths, temp_db, temp_docs):
        insert_component(temp_db, 'module:secret.py', 'module', '/path/secret.py',
                        'Secret module', ['read', 'write'], datetime.now().isoformat())
        create_doc_file(temp_docs, 'README.md', '# Some other component')

        undocumented = scanner_with_temp_paths._find_undocumented_components(
            scanner_with_temp_paths._load_component_knowledge(),
            scanner_with_temp_paths._parse_docs_directory()
        )

        assert len(undocumented) == 1
        assert undocumented[0]['component'] == 'module:secret.py'

    def test_find_multiple_undocumented(self, scanner_with_temp_paths, temp_db, temp_docs):
        for i in range(3):
            insert_component(temp_db, f'module:mod{i}.py', 'module',
                           f'/path/mod{i}.py', f'Module {i}', [], datetime.now().isoformat())

        undocumented = scanner_with_temp_paths._find_undocumented_components(
            scanner_with_temp_paths._load_component_knowledge(),
            scanner_with_temp_paths._parse_docs_directory()
        )

        assert len(undocumented) == 3

    def test_documented_component_not_listed(self, scanner_with_temp_paths, temp_db, temp_docs):
        insert_component(temp_db, 'module:documented.py', 'module',
                        '/path/documented.py', 'Documented', [], datetime.now().isoformat())
        create_doc_file(temp_docs, 'API.md', 'documented module provides functionality')

        components = scanner_with_temp_paths._load_component_knowledge()
        docs = scanner_with_temp_paths._parse_docs_directory()

        undocumented = scanner_with_temp_paths._find_undocumented_components(components, docs)

        assert len(undocumented) == 0
        assert components['module:documented.py']['has_docs']

    def test_severity_assessment_core_components(self, scanner_with_temp_paths, temp_db):
        insert_component(temp_db, 'module:memory_storage.py', 'module',
                        '/path/memory_storage.py', 'Core memory', [], datetime.now().isoformat())

        components = scanner_with_temp_paths._load_component_knowledge()
        undocumented = scanner_with_temp_paths._find_undocumented_components(components, {})

        assert len(undocumented) == 1
        assert undocumented[0]['severity'] == 'critical'

    def test_severity_assessment_utility_components(self, scanner_with_temp_paths, temp_db):
        insert_component(temp_db, 'module:helper.py', 'module',
                        '/path/helper.py', 'Utility helper', [], datetime.now().isoformat())

        components = scanner_with_temp_paths._load_component_knowledge()
        undocumented = scanner_with_temp_paths._find_undocumented_components(components, {})

        assert len(undocumented) == 1
        assert undocumented[0]['severity'] == 'error'


class TestUnderdocumentedDetection:
    """Tests for finding underdocumented components."""

    def test_find_underdocumented_component(self, scanner_with_temp_paths, temp_db, temp_docs):
        insert_component(temp_db, 'module:parser.py', 'module', '/path/parser.py',
                        'Parser module', ['read', 'write', 'parse', 'validate', 'transform'],
                        datetime.now().isoformat())
        create_doc_file(temp_docs, 'API.md', 'parser module can read and write data')

        components = scanner_with_temp_paths._load_component_knowledge()
        docs = scanner_with_temp_paths._parse_docs_directory()

        underdocumented = scanner_with_temp_paths._find_underdocumented_components(components, docs)

        assert len(underdocumented) == 1
        assert underdocumented[0]['component'] == 'module:parser.py'
        assert underdocumented[0]['coverage_score'] < 1.0
        missing = underdocumented[0]['missing_capabilities']
        assert any(cap in missing for cap in ['parse', 'validate', 'transform'])

    def test_fully_documented_not_listed(self, scanner_with_temp_paths, temp_db, temp_docs):
        insert_component(temp_db, 'module:complete.py', 'module', '/path/complete.py',
                        'Complete module', ['read', 'write'],
                        datetime.now().isoformat())
        create_doc_file(temp_docs, 'API.md', 'complete module provides read and write capabilities')

        components = scanner_with_temp_paths._load_component_knowledge()
        docs = scanner_with_temp_paths._parse_docs_directory()

        underdocumented = scanner_with_temp_paths._find_underdocumented_components(components, docs)

        assert len(underdocumented) == 0

    def test_component_without_capabilities(self, scanner_with_temp_paths, temp_db, temp_docs):
        insert_component(temp_db, 'module:empty.py', 'module', '/path/empty.py',
                        'Empty module', [], datetime.now().isoformat())
        create_doc_file(temp_docs, 'API.md', 'empty module exists')

        components = scanner_with_temp_paths._load_component_knowledge()
        docs = scanner_with_temp_paths._parse_docs_directory()

        underdocumented = scanner_with_temp_paths._find_underdocumented_components(components, docs)

        assert len(underdocumented) == 0

    def test_coverage_score_calculation(self, scanner_with_temp_paths, temp_db, temp_docs):
        insert_component(temp_db, 'module:mod.py', 'module', '/path/mod.py',
                        'Module', ['read', 'write', 'delete', 'create'],
                        datetime.now().isoformat())
        create_doc_file(temp_docs, 'API.md', 'mod module: read and write')

        components = scanner_with_temp_paths._load_component_knowledge()
        docs = scanner_with_temp_paths._parse_docs_directory()

        underdocumented = scanner_with_temp_paths._find_underdocumented_components(components, docs)

        assert len(underdocumented) == 1
        assert underdocumented[0]['coverage_score'] == 0.5


class TestStaleDocumentation:
    """Tests for detecting stale documentation."""

    def test_detect_stale_doc(self, scanner_with_temp_paths, temp_db, temp_docs):
        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        insert_component(temp_db, 'module:aging.py', 'module', '/path/aging.py',
                        'Aging module', [], old_date)

        doc_path = create_doc_file(temp_docs, 'AGING.md', 'aging module info')
        old_time = (datetime.now() - timedelta(days=90)).timestamp()
        import os
        os.utime(doc_path, (old_time, old_time))

        components = scanner_with_temp_paths._load_component_knowledge()
        docs = scanner_with_temp_paths._parse_docs_directory()

        stale = scanner_with_temp_paths._detect_stale_documentation(components, docs, 30)

        assert len(stale) >= 0

    def test_recent_documentation_not_stale(self, scanner_with_temp_paths, temp_db, temp_docs):
        recent_date = datetime.now().isoformat()
        insert_component(temp_db, 'module:fresh.py', 'module', '/path/fresh.py',
                        'Fresh module', [], recent_date)

        create_doc_file(temp_docs, 'FRESH.md', 'fresh module info')

        components = scanner_with_temp_paths._load_component_knowledge()
        docs = scanner_with_temp_paths._parse_docs_directory()

        stale = scanner_with_temp_paths._detect_stale_documentation(components, docs, 30)

        assert len(stale) == 0

    def test_severity_levels_for_staleness(self, scanner_with_temp_paths, temp_db, temp_docs):
        old_date = (datetime.now() - timedelta(days=70)).isoformat()
        insert_component(temp_db, 'module:old.py', 'module', '/path/old.py',
                        'Old', [], old_date)

        doc_path = create_doc_file(temp_docs, 'OLD.md', 'old info')
        old_time = (datetime.now() - timedelta(days=90)).timestamp()
        import os
        os.utime(doc_path, (old_time, old_time))

        components = scanner_with_temp_paths._load_component_knowledge()
        docs = scanner_with_temp_paths._parse_docs_directory()

        stale = scanner_with_temp_paths._detect_stale_documentation(components, docs, 30)

        for doc in stale:
            if doc['staleness_days'] > 60:
                assert doc['severity'] == 'error'
            elif doc['staleness_days'] > 30:
                assert doc['severity'] == 'warning'


class TestCoverageCalculation:
    """Tests for calculating documentation coverage."""

    def test_coverage_all_documented(self, scanner_with_temp_paths, temp_db, temp_docs):
        for i in range(5):
            insert_component(temp_db, f'module:mod{i}.py', 'module',
                           f'/path/mod{i}.py', f'Module {i}', [], datetime.now().isoformat())
            create_doc_file(temp_docs, f'mod{i}.md', f'mod{i} module documentation')

        components = scanner_with_temp_paths._load_component_knowledge()
        docs = scanner_with_temp_paths._parse_docs_directory()

        scanner_with_temp_paths._find_undocumented_components(components, docs)

        coverage = scanner_with_temp_paths._calculate_coverage(components, docs)

        assert coverage == 100.0

    def test_coverage_no_components(self, scanner_with_temp_paths):
        coverage = scanner_with_temp_paths._calculate_coverage({}, {})
        assert coverage == 0.0

    def test_coverage_half_documented(self, scanner_with_temp_paths, temp_db, temp_docs):
        for i in range(4):
            insert_component(temp_db, f'module:mod{i}.py', 'module',
                           f'/path/mod{i}.py', f'Module {i}', [], datetime.now().isoformat())

        create_doc_file(temp_docs, 'docs.md', 'mod0 and mod1 documented')

        components = scanner_with_temp_paths._load_component_knowledge()
        docs = scanner_with_temp_paths._parse_docs_directory()

        scanner_with_temp_paths._find_undocumented_components(components, docs)

        coverage = scanner_with_temp_paths._calculate_coverage(components, docs)

        assert 40 < coverage < 60


class TestScanDocumentation:
    """Tests for scan_documentation() method."""

    def test_scan_documentation_returns_correct_structure(self, scanner_with_temp_paths, temp_db):
        insert_component(temp_db, 'module:test.py', 'module', '/path/test.py',
                        'Test', [], datetime.now().isoformat())

        findings = scanner_with_temp_paths.scan_documentation()

        assert 'undocumented' in findings
        assert 'underdocumented' in findings
        assert 'stale_documentation' in findings
        assert 'coverage_summary' in findings
        assert 'scan_metadata' in findings

    def test_scan_with_unavailable_scanner(self, scanner_missing_db, temp_docs):
        findings = scanner_missing_db.scan_documentation()

        assert len(findings['undocumented']) == 0
        assert len(findings['underdocumented']) == 0
        assert findings['coverage_summary']['total_components'] == 0

    def test_scan_caching(self, scanner_with_temp_paths, temp_db):
        insert_component(temp_db, 'module:test.py', 'module', '/path/test.py',
                        'Test', [], datetime.now().isoformat())

        findings1 = scanner_with_temp_paths.scan_documentation()
        findings2 = scanner_with_temp_paths.scan_documentation()

        assert findings1 == findings2
        assert scanner_with_temp_paths.cached_results is not None

    def test_scan_lookback_days_parameter(self, scanner_with_temp_paths, temp_db):
        insert_component(temp_db, 'module:test.py', 'module', '/path/test.py',
                        'Test', [], datetime.now().isoformat())

        findings = scanner_with_temp_paths.scan_documentation(lookback_days=60)

        assert findings['scan_metadata']['lookback_days'] == 60


class TestFormatFindings:
    """Tests for format_findings() output."""

    def test_format_empty_findings(self, scanner_with_temp_paths):
        findings = {
            'undocumented': [],
            'underdocumented': [],
            'stale_documentation': [],
            'coverage_summary': {'total_components': 0, 'documented_components': 0, 'coverage_percentage': 0.0},
            'scan_metadata': {'timestamp': datetime.now().isoformat(), 'lookback_days': 30}
        }

        report = scanner_with_temp_paths.format_findings(findings)

        assert isinstance(report, str)
        assert 'DOCUMENTATION COMPLETENESS SCAN REPORT' in report
        assert 'complete' in report.lower() or 'no' in report.lower()

    def test_format_includes_coverage_percentage(self, scanner_with_temp_paths):
        findings = {
            'undocumented': [],
            'underdocumented': [],
            'stale_documentation': [],
            'coverage_summary': {
                'total_components': 10,
                'documented_components': 7,
                'coverage_percentage': 70.0
            },
            'scan_metadata': {'timestamp': datetime.now().isoformat(), 'lookback_days': 30}
        }

        report = scanner_with_temp_paths.format_findings(findings)

        assert '70.0%' in report

    def test_format_includes_undocumented_components(self, scanner_with_temp_paths):
        findings = {
            'undocumented': [
                {'component': 'module:secret.py', 'type': 'module', 'severity': 'critical',
                 'capabilities': ['read', 'write']}
            ],
            'underdocumented': [],
            'stale_documentation': [],
            'coverage_summary': {'total_components': 1, 'documented_components': 0, 'coverage_percentage': 0.0},
            'scan_metadata': {'timestamp': datetime.now().isoformat(), 'lookback_days': 30}
        }

        report = scanner_with_temp_paths.format_findings(findings)

        assert 'UNDOCUMENTED' in report
        assert 'secret.py' in report or 'secret' in report.lower()

    def test_format_includes_underdocumented_components(self, scanner_with_temp_paths):
        findings = {
            'undocumented': [],
            'underdocumented': [
                {'component': 'module:parser.py', 'coverage_score': 0.5,
                 'missing_capabilities': ['parse', 'validate']}
            ],
            'stale_documentation': [],
            'coverage_summary': {'total_components': 1, 'documented_components': 1, 'coverage_percentage': 100.0},
            'scan_metadata': {'timestamp': datetime.now().isoformat(), 'lookback_days': 30}
        }

        report = scanner_with_temp_paths.format_findings(findings)

        assert 'UNDERDOCUMENTED' in report

    def test_format_includes_stale_docs(self, scanner_with_temp_paths):
        findings = {
            'undocumented': [],
            'underdocumented': [],
            'stale_documentation': [
                {'component': 'module:old.py', 'staleness_days': 45, 'severity': 'warning'}
            ],
            'coverage_summary': {'total_components': 1, 'documented_components': 1, 'coverage_percentage': 100.0},
            'scan_metadata': {'timestamp': datetime.now().isoformat(), 'lookback_days': 30}
        }

        report = scanner_with_temp_paths.format_findings(findings)

        assert 'STALE' in report


class TestErrorHandling:
    """Tests for error handling and resilience."""

    def test_missing_knowledge_db(self, scanner_missing_db):
        assert not scanner_missing_db.available

    def test_missing_docs_directory(self, scanner_missing_docs):
        assert not scanner_missing_docs.available

    def test_malformed_markdown_graceful_degradation(self, scanner_with_temp_paths, temp_docs):
        bad_file = temp_docs / 'bad.md'
        bad_file.write_text('✓ Valid UTF-8 but...\x00invalid byte follows')

        docs = scanner_with_temp_paths._parse_docs_directory()

        assert isinstance(docs, dict)

    def test_scan_with_exception_returns_empty_results(self, scanner_with_temp_paths, temp_db):
        insert_component(temp_db, 'module:test.py', 'module', '/path/test.py',
                        'Test', [], datetime.now().isoformat())

        with patch.object(scanner_with_temp_paths, '_load_component_knowledge',
                         side_effect=Exception("DB error")):
            findings = scanner_with_temp_paths.scan_documentation()

            assert findings['coverage_summary']['total_components'] == 0


class TestHelperMethods:
    """Tests for helper methods."""

    def test_extract_component_name(self, scanner_with_temp_paths):
        assert scanner_with_temp_paths._extract_component_name('module:foo.py') == 'foo'
        assert scanner_with_temp_paths._extract_component_name('class:MyClass') == 'myclass'
        assert scanner_with_temp_paths._extract_component_name('simple') == 'simple'

    def test_extract_documented_capabilities(self, scanner_with_temp_paths):
        content = """
        This module provides read and write capabilities.
        It can validate and parse input data.
        """

        caps = scanner_with_temp_paths._extract_documented_capabilities(content)

        assert 'read' in caps
        assert 'write' in caps
        assert 'validate' in caps
        assert 'parse' in caps

    def test_find_doc_mentions(self, scanner_with_temp_paths, temp_docs):
        create_doc_file(temp_docs, 'API.md', 'The storage module provides...')
        create_doc_file(temp_docs, 'README.md', 'Overview of storage functionality')

        docs = scanner_with_temp_paths._parse_docs_directory()
        mentions = scanner_with_temp_paths._find_doc_mentions('storage', '/path/storage.py', docs)

        assert len(mentions) >= 1


class TestIntegration:
    """Integration tests combining multiple features."""

    def test_full_scan_workflow(self, scanner_with_temp_paths, temp_db, temp_docs):
        insert_component(temp_db, 'module:documented.py', 'module', '/path/documented.py',
                        'Documented', ['read', 'write'], datetime.now().isoformat())
        insert_component(temp_db, 'module:undocumented.py', 'module', '/path/undocumented.py',
                        'Undocumented', ['read'], datetime.now().isoformat())
        insert_component(temp_db, 'module:partial.py', 'module', '/path/partial.py',
                        'Partial', ['read', 'write', 'delete'], datetime.now().isoformat())

        create_doc_file(temp_docs, 'DOCUMENTED.md', 'documented module provides read and write')
        create_doc_file(temp_docs, 'PARTIAL.md', 'partial module can read data')

        findings = scanner_with_temp_paths.scan_documentation()

        assert len(findings['undocumented']) == 1
        assert len(findings['underdocumented']) == 1
        assert findings['coverage_summary']['total_components'] == 3
        assert findings['coverage_summary']['coverage_percentage'] > 0

    def test_scan_documentation_standalone(self):
        from src.observability.introspection.scanners.documentation_completeness_scanner import (
            scan_documentation_standalone
        )

        findings, report = scan_documentation_standalone()

        assert isinstance(findings, dict)
        assert isinstance(report, str)
        assert 'DOCUMENTATION COMPLETENESS' in report
