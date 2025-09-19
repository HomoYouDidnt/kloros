"""Export helpers tests."""

import pytest

pytest.importorskip("clip_scout")

import json
from pathlib import Path

from clip_scout.config import ExportCfg
from clip_scout.export import export_clips, write_csv_json
from clip_scout.types import Clip


def test_export_and_metadata(monkeypatch, tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"data")

    clip = Clip(start=1.0, end=4.5, score=0.9, tags=["boss"], sources=["transcript", "audio"])

    called = {}

    def fake_smart_cut(**kwargs):
        called.setdefault("destinations", []).append(Path(kwargs["destination"]))

    monkeypatch.setattr("clip_scout.export.smart_cut", fake_smart_cut)
    monkeypatch.setattr("clip_scout.export._timestamp", lambda: "20250101_120000")

    out_dir = tmp_path / "run"
    paths = export_clips(source, [clip], out_dir, ExportCfg(), dry_run=False)

    assert len(paths) == 1
    assert paths[0].name.startswith("20250101_120000_001_boss_0p90")
    assert called["destinations"][0] == paths[0]

    write_csv_json([clip], paths, out_dir, source)
    clips_json = out_dir / "clips.json"
    clips_csv = out_dir / "clips.csv"

    payload = json.loads(clips_json.read_text())
    assert payload[0]["source"] == str(source)
    assert payload[0]["filename"] == paths[0].name
    assert payload[0]["tags"] == ["boss"]

    csv_lines = clips_csv.read_text().splitlines()
    assert csv_lines[0] == "source,start,end,duration,score,tags,filename"
    assert str(source) in csv_lines[1]
    assert "boss" in csv_lines[1]
