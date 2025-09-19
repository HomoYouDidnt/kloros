"""Tests for EDL export."""

import pytest

pytest.importorskip("clip_scout.timeline")

from clip_scout.timeline import write_edl
from clip_scout.types import Clip, MediaProbe


def test_write_edl(monkeypatch, tmp_path):
    clips = [
        Clip(start=0.0, end=3.0, score=0.8, tags=["boss"], sources=["transcript"]),
        Clip(start=5.0, end=9.5, score=0.7, tags=[], sources=["audio"]),
    ]

    def fake_probe(path):
        return MediaProbe(duration=600.0, fps=24.0, samplerate=48000)

    monkeypatch.setattr("clip_scout.timeline.probe_media", fake_probe)

    out_path = tmp_path / "timeline.edl"
    write_edl(clips, tmp_path / "source.mp4", out_path)

    content = out_path.read_text().splitlines()
    assert content[0] == "TITLE: clip-scout"
    assert content[1] == "FCM: NON-DROP FRAME"
    assert "000" in content[2]
    assert "001" in content[4]
