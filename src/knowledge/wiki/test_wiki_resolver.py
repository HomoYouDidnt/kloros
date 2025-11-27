"""
Test suite for wiki_resolver module.

Tests lexical matching, frontmatter parsing, section extraction,
caching behavior, and edge cases.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json
import yaml

from wiki_resolver import WikiItem, WikiContext, WikiResolver


@pytest.fixture
def resolver():
    """Create a WikiResolver instance with mock paths."""
    return WikiResolver(wiki_dir="/home/kloros/wiki")


@pytest.fixture
def sample_capability_content():
    """Sample markdown content for a capability."""
    return """---
doc_type: capability
capability_id: latency.monitoring
status: enabled
last_updated: '2025-11-22T18:32:26.488835'
drift_status: ok
---
# latency.monitoring

## Purpose

Provides: monitoring, telemetry

Kind: service

## Scope

Documentation: src/monitoring/README.md

Tests: test_monitoring.py

## Implementations

Module dependencies: telemetry.core

Preconditions:
- path:/home/kloros/src/monitoring/__init__.py readable

## Telemetry

Health check: `bash:test -f /home/kloros/src/monitoring/__init__.py`

Cost:
- CPU: 10
- Memory: 512 MB
- Risk: medium

## Drift Status

**Status:** OK

All preconditions are satisfied.
"""


@pytest.fixture
def sample_index():
    """Sample index.json content."""
    return {
        "version": 1,
        "modules": {
            "audio": {
                "module_id": "audio",
                "code_paths": ["audio/__init__.py"],
                "wiki_status": "missing",
            },
            "kloros_voice_streaming": {
                "module_id": "kloros_voice_streaming",
                "code_paths": ["kloros/__init__.py"],
                "wiki_status": "missing",
            },
        }
    }


class TestWikiItemDataclass:
    """Tests for WikiItem dataclass."""

    def test_wiki_item_creation_minimal(self):
        item = WikiItem(
            item_type="capability",
            item_id="test.capability",
            drift_status="ok"
        )
        assert item.item_type == "capability"
        assert item.item_id == "test.capability"
        assert item.drift_status == "ok"
        assert item.confidence == 1.0
        assert item.frontmatter == {}
        assert item.body_sections == {}

    def test_wiki_item_creation_full(self):
        frontmatter = {"status": "enabled"}
        sections = {"Purpose": "Test purpose"}
        item = WikiItem(
            item_type="module",
            item_id="test.module",
            drift_status="missing",
            confidence=0.8,
            frontmatter=frontmatter,
            body_sections=sections
        )
        assert item.item_type == "module"
        assert item.confidence == 0.8
        assert item.frontmatter == frontmatter
        assert item.body_sections == sections


class TestWikiContextDataclass:
    """Tests for WikiContext dataclass."""

    def test_wiki_context_empty(self):
        context = WikiContext()
        assert context.items == []

    def test_wiki_context_with_items(self):
        item1 = WikiItem("capability", "cap1", "ok")
        item2 = WikiItem("module", "mod1", "missing")
        context = WikiContext(items=[item1, item2])
        assert len(context.items) == 2
        assert context.items[0].item_id == "cap1"
        assert context.items[1].item_id == "mod1"


class TestMarkdownParsing:
    """Tests for YAML frontmatter and markdown parsing."""

    def test_parse_markdown_with_valid_frontmatter(self, sample_capability_content):
        frontmatter, body = WikiResolver._parse_markdown(sample_capability_content)
        assert frontmatter["capability_id"] == "latency.monitoring"
        assert frontmatter["status"] == "enabled"
        assert frontmatter["drift_status"] == "ok"
        assert "# latency.monitoring" in body
        assert body.startswith("# latency.monitoring")

    def test_parse_markdown_without_frontmatter(self):
        content = "# Title\n\nSome content"
        frontmatter, body = WikiResolver._parse_markdown(content)
        assert frontmatter == {}
        assert body == content

    def test_parse_markdown_incomplete_frontmatter(self):
        content = "---\nkey: value\n\nContent without closing ---"
        frontmatter, body = WikiResolver._parse_markdown(content)
        assert frontmatter == {}
        assert body == content

    def test_parse_markdown_invalid_yaml(self):
        content = "---\nkey: [unclosed\n---\nBody"
        frontmatter, body = WikiResolver._parse_markdown(content)
        assert frontmatter == {}
        assert "Body" in body


class TestSectionExtraction:
    """Tests for extracting markdown sections."""

    def test_extract_sections_single_section(self):
        body = """## Purpose

This is the purpose section.

Some more details."""
        sections = WikiResolver._extract_sections(body)
        assert "Purpose" in sections
        assert "This is the purpose section" in sections["Purpose"]

    def test_extract_sections_multiple_sections(self):
        body = """## Purpose

Purpose content here.

## Scope

Scope content here.

## Implementations

Implementation details."""
        sections = WikiResolver._extract_sections(body)
        assert len(sections) == 3
        assert "Purpose" in sections
        assert "Scope" in sections
        assert "Implementations" in sections
        assert "Purpose content" in sections["Purpose"]
        assert "Scope content" in sections["Scope"]

    def test_extract_sections_empty_section(self):
        body = """## Purpose

## Scope

Some scope content."""
        sections = WikiResolver._extract_sections(body)
        assert "Purpose" in sections
        assert "Scope" in sections
        assert sections["Purpose"].strip() == ""

    def test_extract_sections_no_sections(self):
        body = "Just some text without any sections"
        sections = WikiResolver._extract_sections(body)
        assert sections == {}


class TestLexicalMatching:
    """Tests for query matching against capabilities and modules."""

    @patch('wiki_resolver.Path.glob')
    def test_match_query_exact_capability_id(self, mock_glob, resolver):
        mock_glob.return_value = [
            Path("/home/kloros/wiki/capabilities/audio.output.md"),
            Path("/home/kloros/wiki/capabilities/latency.monitoring.md"),
        ]
        with patch.object(resolver, '_load_index', return_value={"modules": {}}):
            matches = resolver._match_query("audio.output")
            assert "audio.output" in matches

    @patch('wiki_resolver.Path.glob')
    def test_match_query_partial_capability_match(self, mock_glob, resolver):
        mock_glob.return_value = [
            Path("/home/kloros/wiki/capabilities/audio.output.md"),
            Path("/home/kloros/wiki/capabilities/latency.monitoring.md"),
        ]
        with patch.object(resolver, '_load_index', return_value={"modules": {}}):
            matches = resolver._match_query("latency monitoring")
            assert "latency.monitoring" in matches

    @patch('wiki_resolver.Path.glob')
    def test_match_query_module_id(self, mock_glob, resolver, sample_index):
        mock_glob.return_value = []
        with patch.object(resolver, '_load_index', return_value=sample_index):
            matches = resolver._match_query("kloros_voice_streaming")
            assert "kloros_voice_streaming" in matches

    @patch('wiki_resolver.Path.glob')
    def test_match_query_no_matches(self, mock_glob, resolver):
        mock_glob.return_value = []
        with patch.object(resolver, '_load_index', return_value={"modules": {}}):
            matches = resolver._match_query("nonexistent query")
            assert matches == []

    @patch('wiki_resolver.Path.glob')
    def test_match_query_case_insensitive(self, mock_glob, resolver):
        mock_glob.return_value = [
            Path("/home/kloros/wiki/capabilities/Audio.Output.md"),
        ]
        with patch.object(resolver, '_load_index', return_value={"modules": {}}):
            matches = resolver._match_query("AUDIO OUTPUT")
            assert "Audio.Output" in matches


class TestLoadCapabilityFile:
    """Tests for loading and caching capability files."""

    @patch('wiki_resolver.Path.exists')
    @patch('wiki_resolver.Path.read_text')
    def test_load_capability_file_success(self, mock_read, mock_exists, resolver, sample_capability_content):
        mock_exists.return_value = True
        mock_read.return_value = sample_capability_content

        frontmatter, sections = resolver._load_capability_file("latency.monitoring")
        assert frontmatter["capability_id"] == "latency.monitoring"
        assert "Purpose" in sections
        assert "Scope" in sections

    @patch('wiki_resolver.Path.exists')
    def test_load_capability_file_missing(self, mock_exists, resolver):
        mock_exists.return_value = False
        frontmatter, sections = resolver._load_capability_file("nonexistent")
        assert frontmatter == {}
        assert sections == {}

    @patch('wiki_resolver.Path.exists')
    @patch('wiki_resolver.Path.read_text')
    def test_load_capability_file_caching(self, mock_read, mock_exists, resolver, sample_capability_content):
        mock_exists.return_value = True
        mock_read.return_value = sample_capability_content

        resolver._load_capability_file("latency.monitoring")
        assert "latency.monitoring" in resolver._frontmatter_cache
        assert "latency.monitoring" in resolver._body_cache

        resolver._load_capability_file("latency.monitoring")
        assert mock_read.call_count == 1


class TestIndexCaching:
    """Tests for index.json caching."""

    def test_load_index_caching(self, resolver, sample_index):
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(sample_index)
            with patch('json.load', return_value=sample_index):
                index1 = resolver._load_index()
                index2 = resolver._load_index()

                assert index1 is index2
                assert resolver._index_cache is not None


class TestDriftStatusResolution:
    """Tests for drift status determination."""

    def test_get_drift_status_from_frontmatter(self, resolver):
        frontmatter = {"drift_status": "stale"}
        status = resolver._get_drift_status("test.cap", frontmatter)
        assert status == "stale"

    def test_get_drift_status_default(self, resolver):
        frontmatter = {"status": "enabled"}
        status = resolver._get_drift_status("test.cap", frontmatter)
        assert status == "ok"


class TestGetContext:
    """Tests for the main get_context function."""

    @patch('wiki_resolver.WikiResolver._match_query')
    @patch('wiki_resolver.WikiResolver._load_capability_file')
    def test_get_context_capability_match(self, mock_load, mock_match, resolver):
        mock_match.return_value = ["audio.output"]
        mock_load.return_value = (
            {"drift_status": "ok", "capability_id": "audio.output"},
            {"Purpose": "Audio output capability"}
        )

        with patch('wiki_resolver.Path.exists', return_value=True):
            context = resolver.get_context("audio output")

        assert len(context.items) == 1
        assert context.items[0].item_type == "capability"
        assert context.items[0].item_id == "audio.output"
        assert context.items[0].drift_status == "ok"

    @patch('wiki_resolver.WikiResolver._match_query')
    @patch('wiki_resolver.WikiResolver._load_index')
    def test_get_context_module_match(self, mock_index, mock_match, resolver):
        mock_match.return_value = ["audio"]
        mock_index.return_value = {
            "modules": {
                "audio": {
                    "module_id": "audio",
                    "code_paths": ["audio/__init__.py"],
                    "wiki_status": "missing",
                }
            }
        }

        with patch('wiki_resolver.Path.exists', return_value=False):
            context = resolver.get_context("audio")

        assert len(context.items) == 1
        assert context.items[0].item_type == "module"
        assert context.items[0].item_id == "audio"
        assert context.items[0].drift_status == "missing"

    @patch('wiki_resolver.WikiResolver._match_query')
    def test_get_context_no_matches(self, mock_match, resolver):
        mock_match.return_value = []
        context = resolver.get_context("nonexistent")
        assert context.items == []


class TestIntegration:
    """Integration tests with real filesystem operations."""

    def test_resolver_with_real_wiki(self):
        resolver = WikiResolver(wiki_dir="/home/kloros/wiki")
        assert resolver.wiki_dir.exists()
        assert resolver.index_path.exists()
        assert resolver.capabilities_dir.exists()

    def test_load_real_index(self):
        resolver = WikiResolver(wiki_dir="/home/kloros/wiki")
        index = resolver._load_index()
        assert "modules" in index
        assert len(index["modules"]) > 0

    def test_load_real_capability(self):
        resolver = WikiResolver(wiki_dir="/home/kloros/wiki")
        if resolver.capabilities_dir.glob("*.md"):
            cap_file = next(resolver.capabilities_dir.glob("*.md"))
            cap_id = cap_file.stem
            frontmatter, sections = resolver._load_capability_file(cap_id)
            if frontmatter:
                assert "capability_id" in frontmatter or "doc_type" in frontmatter

    def test_match_real_queries(self):
        resolver = WikiResolver(wiki_dir="/home/kloros/wiki")
        queries = [
            "audio output",
            "latency monitoring",
            "memory",
        ]
        for query in queries:
            context = resolver.get_context(query)

    def test_caching_performance(self):
        resolver = WikiResolver(wiki_dir="/home/kloros/wiki")
        context1 = resolver.get_context("audio")
        context2 = resolver.get_context("audio")
        assert len(resolver._frontmatter_cache) > 0
        assert len(resolver._body_cache) >= 0
