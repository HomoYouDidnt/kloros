"""Tests for review reel builder."""

from pathlib import Path

from clip_scout.review import build_review_reel


def test_build_review_reel_invokes_ffmpeg(monkeypatch, tmp_path):
    src = tmp_path / "source.mp4"
    src.write_bytes(b"vid")

    clip1 = tmp_path / "clips" / "clip1.mp4"
    clip2 = tmp_path / "clips" / "clip2.mp4"
    clip1.parent.mkdir(parents=True, exist_ok=True)
    clip1.write_bytes(b"c1")
    clip2.write_bytes(b"c2")

    captured = {}

    def fake_run(command, *, task):
        captured["command"] = command
        captured["task"] = task
        return None

    monkeypatch.setattr("clip_scout.review._run_command", fake_run)

    out_path = tmp_path / "review.mp4"
    result = build_review_reel(src, [clip1, clip2], out_path)

    assert result == out_path
    cmd = captured["command"]
    assert cmd[0] == "ffmpeg"
    assert "-filter_complex" in cmd
    assert "concat=n=2" in cmd[cmd.index("-filter_complex") + 1]
    assert str(clip1) in cmd
    assert str(clip2) in cmd


def test_build_review_reel_no_clips(tmp_path):
    result = build_review_reel(tmp_path / "src.mp4", [], tmp_path / "out.mp4")
    assert result is None
