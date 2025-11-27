"""
Tests for capability documentation generator and drift detection.
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from .capability_docgen import CapabilityDocgen, DriftDetector


class TestDriftDetector:
    """Test drift detection functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.index = {
            "version": 1,
            "generated_ts": 1000.0,
            "modules": {
                "existing.module": {
                    "module_id": "existing.module",
                    "code_paths": ["existing/module/__init__.py"],
                },
                "chromadb": {
                    "module_id": "chromadb",
                    "code_paths": [],
                },
            },
        }
        self.detector = DriftDetector(self.index)

    def test_detect_drift_ok_with_no_preconditions(self):
        """Test that empty preconditions result in OK status."""
        status, details = self.detector.detect_drift([])
        assert status == "ok"
        assert details == []

    def test_detect_drift_ok_with_path_preconditions(self):
        """Test that path preconditions do not cause drift."""
        preconditions = [
            "path:/home/kloros/some/path readable",
            "path:/home/kloros/another/path rw",
        ]
        status, details = self.detector.detect_drift(preconditions)
        assert status == "ok"
        assert details == []

    def test_detect_drift_ok_with_group_preconditions(self):
        """Test that group preconditions do not cause drift."""
        preconditions = ["group:audio", "group:system"]
        status, details = self.detector.detect_drift(preconditions)
        assert status == "ok"
        assert details == []

    def test_detect_drift_ok_with_existing_module(self):
        """Test that references to indexed modules are OK."""
        preconditions = ["module:existing.module importable"]
        status, details = self.detector.detect_drift(preconditions)
        assert status == "ok"
        assert details == []

    def test_detect_drift_missing_module(self):
        """Test that missing modules are detected."""
        preconditions = ["module:nonexistent.module importable"]
        status, details = self.detector.detect_drift(preconditions)
        assert status == "missing_module"
        assert len(details) == 1
        assert "nonexistent.module" in details[0]

    def test_detect_drift_multiple_modules_one_missing(self):
        """Test detection with multiple modules where one is missing."""
        preconditions = [
            "module:existing.module importable",
            "module:missing.module importable",
        ]
        status, details = self.detector.detect_drift(preconditions)
        assert status == "missing_module"
        assert len(details) == 1
        assert "missing.module" in details[0]

    def test_detect_drift_external_module(self):
        """Test detection of external third-party modules like chromadb."""
        preconditions = ["module:chromadb importable"]
        status, details = self.detector.detect_drift(preconditions)
        assert status == "ok"

    def test_detect_drift_mixed_preconditions(self):
        """Test with mixed precondition types."""
        preconditions = [
            "path:/home/kloros/config.yaml readable",
            "group:audio",
            "module:existing.module importable",
            "command:which python",
            "http:http://localhost:8000",
        ]
        status, details = self.detector.detect_drift(preconditions)
        assert status == "ok"
        assert details == []

    def test_detect_drift_mismatch_unknown_format(self):
        """Test detection of unknown precondition formats."""
        preconditions = ["unknown_format:something"]
        status, details = self.detector.detect_drift(preconditions)
        assert status == "mismatch"
        assert len(details) > 0


class TestCapabilityDocgen:
    """Test capability documentation generation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.yaml_path = Path(self.temp_dir.name) / "test_capabilities.yaml"
        self.index_path = Path(self.temp_dir.name) / "test_index.json"
        self.output_dir = Path(self.temp_dir.name) / "output"

    def teardown_method(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def write_test_yaml(self, capabilities: list):
        """Write test YAML file."""
        with open(self.yaml_path, "w") as f:
            yaml.dump(capabilities, f)

    def write_test_index(self, modules: Dict[str, Any]):
        """Write test index.json file."""
        index = {
            "version": 1,
            "generated_ts": 1000.0,
            "modules": modules,
        }
        with open(self.index_path, "w") as f:
            json.dump(index, f)

    def test_load_capabilities(self):
        """Test loading capabilities from YAML."""
        capabilities = [
            {
                "key": "test.capability",
                "kind": "service",
                "provides": ["feature1"],
                "preconditions": ["path:/test"],
                "enabled": True,
            }
        ]
        self.write_test_yaml(capabilities)
        self.write_test_index({})

        docgen = CapabilityDocgen(str(self.yaml_path), str(self.index_path), str(self.output_dir))
        loaded = docgen.load_capabilities()

        assert len(loaded) == 1
        assert loaded[0]["key"] == "test.capability"

    def test_generate_markdown_with_drift(self):
        """Test markdown generation with drift detection."""
        capabilities = [
            {
                "key": "test.cap",
                "kind": "service",
                "provides": ["feature1"],
                "preconditions": ["module:missing.module importable"],
                "health_check": "test_check",
                "cost": {"cpu": 5, "mem": 256, "risk": "low"},
                "tests": ["test1"],
                "docs": "docs/test.md",
                "enabled": True,
            }
        ]
        self.write_test_yaml(capabilities)
        self.write_test_index({})

        docgen = CapabilityDocgen(str(self.yaml_path), str(self.index_path), str(self.output_dir))
        docgen.load_capabilities()
        docgen.load_index()

        capability = capabilities[0]
        markdown = docgen.generate_markdown(capability, "missing_module", ["Module 'missing.module' not found"])

        assert "---" in markdown
        assert "capability_id: test.cap" in markdown
        assert "drift_status: missing_module" in markdown
        assert "## Purpose" in markdown
        assert "## Implementations" in markdown
        assert "## Drift Status" in markdown
        assert "missing_module" in markdown.lower()

    def test_full_generation_with_mixed_drift(self):
        """Test full generation with mixed drift statuses."""
        capabilities = [
            {
                "key": "good.cap",
                "kind": "service",
                "provides": ["feature"],
                "preconditions": ["path:/test"],
                "enabled": True,
            },
            {
                "key": "bad.cap",
                "kind": "service",
                "provides": ["feature"],
                "preconditions": ["module:missing.module importable"],
                "enabled": True,
            },
        ]
        self.write_test_yaml(capabilities)
        self.write_test_index({})

        docgen = CapabilityDocgen(str(self.yaml_path), str(self.index_path), str(self.output_dir))
        drift_report = docgen.run()

        assert len(drift_report) == 2
        assert drift_report["good.cap"] == "ok"
        assert drift_report["bad.cap"] == "missing_module"
        assert (self.output_dir / "good.cap.md").exists()
        assert (self.output_dir / "bad.cap.md").exists()

    def test_disabled_capability_marked_correctly(self):
        """Test that disabled capabilities are marked as such."""
        capabilities = [
            {
                "key": "disabled.cap",
                "kind": "service",
                "provides": ["feature"],
                "preconditions": [],
                "enabled": False,
            }
        ]
        self.write_test_yaml(capabilities)
        self.write_test_index({})

        docgen = CapabilityDocgen(str(self.yaml_path), str(self.index_path), str(self.output_dir))
        docgen.load_capabilities()
        docgen.load_index()

        markdown = docgen.generate_markdown(capabilities[0], "ok", [])

        assert "status: disabled" in markdown

    def test_enabled_capability_marked_correctly(self):
        """Test that enabled capabilities are marked as such."""
        capabilities = [
            {
                "key": "enabled.cap",
                "kind": "service",
                "provides": ["feature"],
                "preconditions": [],
                "enabled": True,
            }
        ]
        self.write_test_yaml(capabilities)
        self.write_test_index({})

        docgen = CapabilityDocgen(str(self.yaml_path), str(self.index_path), str(self.output_dir))
        docgen.load_capabilities()
        docgen.load_index()

        markdown = docgen.generate_markdown(capabilities[0], "ok", [])

        assert "status: enabled" in markdown

    def test_module_references_extraction(self):
        """Test extraction of module references from preconditions."""
        preconditions = [
            "path:/test",
            "module:module1 importable",
            "module:module2 importable",
            "group:audio",
        ]
        self.write_test_yaml([])
        self.write_test_index({})

        docgen = CapabilityDocgen(str(self.yaml_path), str(self.index_path), str(self.output_dir))

        refs = docgen.extract_module_references(preconditions)

        assert len(refs) == 2
        assert "module1" in refs
        assert "module2" in refs

    def test_capability_with_no_tests(self):
        """Test capability documentation with no tests."""
        capabilities = [
            {
                "key": "no.tests",
                "kind": "service",
                "provides": ["feature"],
                "preconditions": [],
                "enabled": True,
            }
        ]
        self.write_test_yaml(capabilities)
        self.write_test_index({})

        docgen = CapabilityDocgen(str(self.yaml_path), str(self.index_path), str(self.output_dir))
        docgen.load_capabilities()
        docgen.load_index()

        markdown = docgen.generate_markdown(capabilities[0], "ok", [])

        assert "Tests: None" in markdown

    def test_capability_with_tests(self):
        """Test capability documentation with tests."""
        capabilities = [
            {
                "key": "with.tests",
                "kind": "service",
                "provides": ["feature"],
                "preconditions": [],
                "tests": ["test1", "test2"],
                "enabled": True,
            }
        ]
        self.write_test_yaml(capabilities)
        self.write_test_index({})

        docgen = CapabilityDocgen(str(self.yaml_path), str(self.index_path), str(self.output_dir))
        docgen.load_capabilities()
        docgen.load_index()

        markdown = docgen.generate_markdown(capabilities[0], "ok", [])

        assert "- test1" in markdown
        assert "- test2" in markdown


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
