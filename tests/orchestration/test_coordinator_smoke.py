#!/usr/bin/env python3
"""
Smoke tests for coordinator.py - Orchestrator state machine.
"""

import pytest
import os
from unittest.mock import patch

from src.kloros.orchestration.coordinator import (
    tick,
    _in_phase_window,
    _is_orchestration_enabled
)


def test_orchestration_disabled_by_default():
    """Test that orchestration is disabled when env var not set."""
    # Save original
    orig = os.environ.get("KLR_ORCHESTRATION_MODE")

    try:
        # Clear env var
        if "KLR_ORCHESTRATION_MODE" in os.environ:
            del os.environ["KLR_ORCHESTRATION_MODE"]

        assert not _is_orchestration_enabled()

        # Test tick returns DISABLED
        result = tick()
        assert result == "DISABLED"

    finally:
        # Restore
        if orig:
            os.environ["KLR_ORCHESTRATION_MODE"] = orig
        elif "KLR_ORCHESTRATION_MODE" in os.environ:
            del os.environ["KLR_ORCHESTRATION_MODE"]


def test_orchestration_enabled():
    """Test that orchestration is enabled when env var set."""
    orig = os.environ.get("KLR_ORCHESTRATION_MODE")

    try:
        os.environ["KLR_ORCHESTRATION_MODE"] = "enabled"
        assert _is_orchestration_enabled()

    finally:
        if orig:
            os.environ["KLR_ORCHESTRATION_MODE"] = orig
        elif "KLR_ORCHESTRATION_MODE" in os.environ:
            del os.environ["KLR_ORCHESTRATION_MODE"]


def test_in_phase_window():
    """Test PHASE window detection (basic smoke test)."""
    # This just tests that the function doesn't crash
    # Actual value depends on current time
    result = _in_phase_window()
    assert isinstance(result, bool)


@patch('src.kloros.orchestration.coordinator._in_phase_window')
@patch('src.kloros.orchestration.coordinator._phase_done_today')
@patch('src.kloros.orchestration.coordinator._has_new_promotions')
@patch('src.kloros.orchestration.coordinator._has_idle_intents')
def test_tick_noop(mock_intents, mock_promos, mock_phase_done, mock_window):
    """Test tick with no actions needed."""
    orig = os.environ.get("KLR_ORCHESTRATION_MODE")

    try:
        os.environ["KLR_ORCHESTRATION_MODE"] = "enabled"

        # Mock: not in window, no promotions, no intents
        mock_window.return_value = False
        mock_phase_done.return_value = True
        mock_promos.return_value = False
        mock_intents.return_value = False

        result = tick()
        assert result == "NOOP"

    finally:
        if orig:
            os.environ["KLR_ORCHESTRATION_MODE"] = orig
        elif "KLR_ORCHESTRATION_MODE" in os.environ:
            del os.environ["KLR_ORCHESTRATION_MODE"]


def test_tick_disabled():
    """Test tick when orchestration is disabled."""
    orig = os.environ.get("KLR_ORCHESTRATION_MODE")

    try:
        os.environ["KLR_ORCHESTRATION_MODE"] = "disabled"

        result = tick()
        assert result == "DISABLED"

    finally:
        if orig:
            os.environ["KLR_ORCHESTRATION_MODE"] = orig
        elif "KLR_ORCHESTRATION_MODE" in os.environ:
            del os.environ["KLR_ORCHESTRATION_MODE"]
