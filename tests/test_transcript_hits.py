"""Transcript hit detector tests."""

import pytest

pytest.importorskip("clip_scout.detectors.transcript_hits")

from clip_scout.config import KeywordConfig
from clip_scout.detectors.transcript_hits import find_transcript_hits
from clip_scout.types import Segment


def test_find_transcript_hits_matches_keywords():
    segments = [
        Segment(start=5.0, end=8.0, text="That boss fight was insane!"),
        Segment(start=12.0, end=15.0, text="Calm moment"),
    ]
    cfg = KeywordConfig(include=["boss", "insane"], window_seconds=6)

    hits = find_transcript_hits(segments, cfg)

    assert len(hits) == 1
    hit = hits[0]
    assert hit.kind == "transcript"
    assert hit.start == 2.0  # 5.0 - window/2
    assert hit.end == 11.0  # 8.0 + window/2
    assert set(hit.tags) == {"boss", "insane"}


def test_find_transcript_hits_matches_regex():
    segments = [Segment(start=0.0, end=3.0, text="No way he did that!")]
    cfg = KeywordConfig(regex=[r"no way"], window_seconds=4)

    hits = find_transcript_hits(segments, cfg)

    assert len(hits) == 1
    hit = hits[0]
    assert hit.start == 0.0  # clamped
    assert hit.end == 5.0
    assert hit.tags == [r"no way"]


def test_find_transcript_hits_no_matches():
    segments = [Segment(start=0, end=5, text="hello world")]
    hits = find_transcript_hits(segments, KeywordConfig())
    assert hits == []
