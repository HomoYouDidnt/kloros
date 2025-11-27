import pytest
from src.orchestration.registry.capability_scanners.base import CapabilityGap, ScannerMetadata, CapabilityScanner


def test_capability_gap_creation():
    """Test CapabilityGap dataclass creation."""
    gap = CapabilityGap(
        type='external_tool',
        name='ripgrep',
        category='cli_tool',
        reason='Faster log searching',
        alignment_score=0.7,
        install_cost=0.2
    )

    assert gap.type == 'external_tool'
    assert gap.name == 'ripgrep'
    assert gap.alignment_score == 0.7


def test_scanner_metadata_creation():
    """Test ScannerMetadata dataclass creation."""
    metadata = ScannerMetadata(
        name='TestScanner',
        domain='external_tools',
        alignment_baseline=0.6,
        scan_cost=0.15,
        schedule_weight=0.5
    )

    assert metadata.name == 'TestScanner'
    assert metadata.scan_cost == 0.15


def test_capability_scanner_abstract():
    """Test that CapabilityScanner cannot be instantiated."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        scanner = CapabilityScanner()


def test_capability_scanner_should_run():
    """Test default should_run scheduling logic."""
    import time

    class TestScanner(CapabilityScanner):
        def scan(self):
            return []

        def get_metadata(self):
            return ScannerMetadata(
                name='Test',
                domain='test',
                alignment_baseline=0.5,
                scan_cost=0.1,
                schedule_weight=1.0  # Run every hour
            )

    scanner = TestScanner()

    # Should run if last_run was >1 hour ago
    last_run = time.time() - 3700  # 61 minutes ago
    assert scanner.should_run(last_run, idle_budget=0.2) is True

    # Should not run if last_run was recent
    last_run = time.time() - 1800  # 30 minutes ago
    assert scanner.should_run(last_run, idle_budget=0.2) is False

    # Should not run if budget insufficient
    last_run = time.time() - 7200  # 2 hours ago
    assert scanner.should_run(last_run, idle_budget=0.05) is False
