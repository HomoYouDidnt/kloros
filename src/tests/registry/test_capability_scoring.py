import pytest
import time
from src.orchestration.registry.capability_discovery_monitor import CapabilityDiscoveryMonitor
from src.orchestration.registry.capability_scanners.base import CapabilityGap


def test_frequency_score_calculation():
    """Test frequency score based on operation patterns."""
    monitor = CapabilityDiscoveryMonitor()

    monitor.operation_patterns = {
        'grep': [
            {'timestamp': time.time() - 3600, 'file_size': 1000000},
            {'timestamp': time.time() - 7200, 'file_size': 2000000},
            {'timestamp': time.time() - 10800, 'file_size': 1500000},
        ]
    }

    gap = CapabilityGap(
        type='external_tool',
        name='ripgrep',
        category='cli_tool',
        reason='Faster log searching',
        alignment_score=0.7,
        install_cost=0.2,
        metadata={'operation': 'grep'}
    )

    score = monitor._calculate_frequency_score(gap)

    assert 0.0 <= score <= 1.0
    assert score == 0.3


def test_priority_score_calculation():
    """Test hybrid priority score calculation."""
    monitor = CapabilityDiscoveryMonitor()

    gap = CapabilityGap(
        type='external_tool',
        name='ripgrep',
        category='cli_tool',
        reason='Faster log searching',
        alignment_score=0.7,
        install_cost=0.2
    )

    frequency = 0.8
    voi = 0.6
    alignment = gap.alignment_score
    cost = gap.install_cost

    priority = monitor._calculate_priority_score(
        frequency, voi, alignment, cost
    )

    assert 0.0 <= priority <= 1.0

    expected = (0.8 * 0.3) + (0.6 * 0.35) + (0.7 * 0.25) + ((1.0 - 0.2) * 0.1)
    assert abs(priority - expected) < 0.01
