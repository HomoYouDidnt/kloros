"""Shared pytest fixtures for voice zooid testing."""
import sys
import tempfile
from pathlib import Path

import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def fixtures_dir():
    """Return the fixtures directory path."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def test_audio_fixtures(fixtures_dir):
    """Ensure test audio fixtures exist."""
    test_audio_1s = fixtures_dir / "test_audio_1s.wav"
    test_audio_short = fixtures_dir / "test_audio_short.wav"
    test_audio_silent = fixtures_dir / "test_audio_silent.wav"

    if not test_audio_1s.exists() or not test_audio_short.exists() or not test_audio_silent.exists():
        import subprocess
        subprocess.run(
            ["python3", str(fixtures_dir / "generate_test_audio.py")],
            check=True
        )

    return {
        "1s": test_audio_1s,
        "short": test_audio_short,
        "silent": test_audio_silent
    }


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: integration tests using real ChemBus (deselect with '-m \"not integration\"')"
    )
    config.addinivalue_line(
        "markers", "e2e: end-to-end tests with multiple zooids (deselect with '-m \"not e2e\"')"
    )
