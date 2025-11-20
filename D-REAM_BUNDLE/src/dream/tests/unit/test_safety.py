#!/usr/bin/env python3
"""
Unit tests for safety gate module.
"""

import unittest
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from safety.gate import SafetyConfig, SafetyGate


class TestSafetyGate(unittest.TestCase):
    """Test safety gate functionality."""

    def setUp(self):
        """Set up test safety gate."""
        self.config = SafetyConfig(
            allowed_paths=["/tmp/test"],
            blocked_paths=["/etc", "/usr"],
            max_cpu_s=10,
            max_mem_mb=512,
            dry_run=True
        )
        self.gate = SafetyGate(self.config)

    def test_refuses_writes_outside_allowlist(self):
        """Test that writes outside allowlist raise PermissionError."""
        with self.assertRaises(PermissionError):
            self.gate.check_path("/etc/passwd", "write")

        with self.assertRaises(PermissionError):
            self.gate.check_path("/home/other/file", "write")

    def test_allows_writes_in_allowlist(self):
        """Test that writes in allowlist are allowed."""
        # Should not raise
        result = self.gate.check_path("/tmp/test/file.txt", "write")
        self.assertTrue(result)

    def test_blocks_blocked_paths(self):
        """Test that blocked paths are refused."""
        with self.assertRaises(PermissionError):
            self.gate.check_path("/usr/bin/python", "read")

    def test_dry_run_blocks_mutations(self):
        """Test that dry-run mode blocks mutations."""
        self.assertFalse(self.gate.allow_mutation())

        # Non-dry-run allows mutations
        self.gate.cfg.dry_run = False
        self.assertTrue(self.gate.allow_mutation())

    def test_network_blocking(self):
        """Test network access control."""
        with self.assertRaises(PermissionError):
            self.gate.check_network("example.com", 80)

        # Enable network
        self.gate.cfg.allow_network = True
        result = self.gate.check_network("example.com", 80)
        self.assertTrue(result)

    def test_violation_recording(self):
        """Test that violations are recorded."""
        try:
            self.gate.check_path("/etc/passwd", "write")
        except PermissionError:
            pass

        violations = self.gate.get_violations()
        self.assertEqual(len(violations), 1)
        self.assertIn("write blocked", violations[0]['type'])


if __name__ == '__main__':
    unittest.main()
