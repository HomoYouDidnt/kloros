"""Tests for scene cut detector."""

from pathlib import Path

import pytest

from clip_scout.config import SceneCfg
from clip_scout.detectors.scene_cuts import find_scene_windows


class DummyTime:
    def __init__(self, seconds: float):
        self._seconds = seconds

    def get_seconds(self) -> float:
        return self._seconds


class DummySceneManager:
    def __init__(self):
        self.detectors = []

    def add_detector(self, detector):
        self.detectors.append(detector)

    def detect_scenes(self, frame_source):
        self.frame_source = frame_source

    def get_scene_list(self):
        return [
            (DummyTime(0.0), DummyTime(2.0)),
            (DummyTime(2.0), DummyTime(6.5)),
        ]


class DummyVideoManager:
    def __init__(self, sources):
        self.sources = sources
        self.started = False

    def start(self):
        self.started = True

    def release(self):
        self.started = False


class DummyDetector:
    def __init__(self, threshold):
        self.threshold = threshold


@pytest.fixture(autouse=True)
def _patch_scene(monkeypatch):
    monkeypatch.setattr("clip_scout.detectors.scene_cuts.SceneManager", DummySceneManager)
    monkeypatch.setattr("clip_scout.detectors.scene_cuts.VideoManager", DummyVideoManager)
    monkeypatch.setattr("clip_scout.detectors.scene_cuts.ContentDetector", DummyDetector)
    yield


def test_find_scene_windows(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"vid")

    hits = find_scene_windows(video_path, SceneCfg(min_scene_len=3.0, content_threshold=27))

    assert len(hits) == 1
    hit = hits[0]
    assert hit.kind == "scene"
    assert hit.start == 2.0
    assert hit.end == 6.5
    assert hit.score == 0.8
    assert hit.tags == ["scene-cut"]
