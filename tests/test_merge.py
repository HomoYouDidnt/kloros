"""Scoring and merge logic tests."""

import pytest

pytest.importorskip("clip_scout")

from clip_scout.config import PrePostRoll, ThresholdsConfig, WeightsConfig
from clip_scout.scoring import expand_and_clip, iou, merge_by_iou, score_windows
from clip_scout.types import Clip, Hit


def test_iou_basic():
    assert iou((0.0, 2.0), (1.0, 3.0)) == 0.3333333333333333
    assert iou((0.0, 1.0), (2.0, 3.0)) == 0.0


def test_merge_by_iou_merges_same_kind():
    hits = [
        Hit(kind="transcript", start=0.0, end=2.0, score=0.8, tags=["boss"]),
        Hit(kind="transcript", start=1.5, end=3.0, score=0.7, tags=["clutch"]),
    ]
    merged = merge_by_iou(hits, iou_thresh=0.2)
    assert len(merged) == 1
    hit = merged[0]
    assert hit.start == 0.0
    assert hit.end == 3.0
    assert hit.score == 0.8
    assert set(hit.tags) == {"boss", "clutch"}


def test_score_windows_combines_sources():
    hits = [
        Hit(kind="transcript", start=0.0, end=2.0, score=0.9, tags=["boss"]),
        Hit(kind="audio", start=1.0, end=2.5, score=0.8, tags=["audio-peak"]),
        Hit(kind="scene", start=2.4, end=4.0, score=0.7, tags=["scene-cut"]),
    ]
    weights = WeightsConfig(transcript_hit=0.6, audio_peak=0.2, scene_cut=0.2)
    clips = score_windows(hits, weights)
    assert len(clips) == 1
    clip = clips[0]
    assert clip.start == 0.0
    assert clip.end == 4.0
    assert set(clip.tags) == {"boss", "audio-peak", "scene-cut"}
    assert set(clip.sources) == {"transcript", "audio", "scene"}
    assert clip.score <= 1.0


def test_expand_and_clip_respects_thresholds():
    clips = [Clip(start=10.0, end=12.0, score=0.9, tags=["boss"], sources=["transcript"])]
    expanded = expand_and_clip(
        clips,
        prepost=PrePostRoll(pre=3.0, post=4.0),
        thresholds=ThresholdsConfig(min_duration=5.0, max_duration=8.0),
        video_duration=30.0,
    )
    assert len(expanded) == 1
    clip = expanded[0]
    assert clip.start == 7.0
    assert clip.end == 15.0
    assert abs((clip.end - clip.start) - 8.0) < 1e-6
