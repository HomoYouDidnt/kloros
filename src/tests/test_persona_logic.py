"""Tests for persona phrasing and loyalty logic helpers."""

from __future__ import annotations

import json
import re

import pytest

from src.cognition.logic import kloros as logic
from src.governance.persona.kloros import get_line


@pytest.fixture
def ops_log(monkeypatch, tmp_path):
    """Redirect ops.log writes into a temporary location for each test."""
    path = tmp_path / "ops.log"
    monkeypatch.setattr(logic, "OPS_LOG_PATH", path)
    return path


def _read_last_event(log_path):
    assert log_path.exists(), "ops.log should exist"
    data = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert data, "expected log_event to write at least one line"
    return json.loads(data[-1])


def test_should_prioritize_interactive_tasks_raise_priority(ops_log):
    decision = logic.should_prioritize(
        "operator-1",
        {"kind": "interactive", "name": "voice_command"},
    )
    assert decision is True
    payload = _read_last_event(ops_log)
    assert payload["event"] == "priority_eval"
    assert payload["user"] == "operator-1"
    assert payload["interactive"] is True
    assert payload["decision"] is True


def test_should_prioritize_handles_missing_task(ops_log):
    decision = logic.should_prioritize("operator-2", None)
    assert decision is False
    payload = _read_last_event(ops_log)
    assert payload["event"] == "priority_eval"
    assert payload["reason"] == "no_task"
    assert payload["decision"] is False


def test_protective_choice_prefers_low_risk_option(ops_log):
    choice = logic.protective_choice(
        (
            {"name": "run_batch", "risk": 0.7},
            {"name": "safe_refusal", "risk": 0.1},
        ),
        {"id": "operator-3"},
    )
    assert choice["name"] == "safe_refusal"
    payload = _read_last_event(ops_log)
    assert payload["event"] == "protective_choice"
    assert payload["chosen"] == "safe_refusal"
    assert payload["risk"] == pytest.approx(0.1, rel=1e-3)


@pytest.mark.parametrize(
    "kind,context",
    [
        ("boot", {"detail": "Systems nominal."}),
        ("error", {"issue": "Model failed"}),
        ("success", {"result": "Task completed"}),
        ("refuse", {"reason": "Too risky", "fallback": " choose another plan"}),
        ("quip", {"line": "Keep it short"}),
    ],
)
def test_persona_lines_are_concise_and_aloof(kind, context):
    line = get_line(kind, context)
    assert line, "persona line should not be empty"
    assert line[-1] in ".!?"
    assert "!" not in line, "persona avoids exuberant punctuation"
    lowered = line.lower()
    for forbidden in (" love", " adore", " loyal", " loyalty"):
        assert forbidden not in lowered, f"persona leaked forbidden term in: {line}"
    segments = [seg for seg in re.split(r"[.!?]", line) if seg.strip()]
    assert len(segments) <= 2, f"persona response too long: {line}"


def test_get_line_rejects_unknown_kind():
    with pytest.raises(ValueError):
        get_line("unknown", {})
