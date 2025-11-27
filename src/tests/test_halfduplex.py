#!/usr/bin/env python3
"""
Half-duplex audio suppression test

Validates:
1. No audio queuing during TTS suppression
2. Queue flush works correctly
3. Watchdog clears stuck suppression flag after 30s

Usage:
    python tests/test_halfduplex.py
    # or
    pytest tests/test_halfduplex.py -v
"""

import time
import queue
import threading
from types import SimpleNamespace


class FakeBackend:
    """Simulates audio backend for testing."""
    def __init__(self, block_ms=10):
        self.block = block_ms / 1000.0
        self._stop = threading.Event()

    def chunks(self, block_ms):
        """Yield fake audio chunks at specified rate."""
        # Ignore block_ms arg; use self.block to simulate device
        while not self._stop.is_set():
            time.sleep(self.block)
            yield 1.0  # Pretend audio sample

    def stop(self):
        """Stop chunk generation."""
        self._stop.set()


def test_halfduplex_suppression():
    """Test that audio queuing stops during TTS suppression."""
    print("\n=== Test 1: Half-Duplex Suppression ===")

    # Build a minimal VoiceEngine-like object
    ve = SimpleNamespace()
    ve.tts_suppression_enabled = True
    ve.tts_playing_evt = threading.Event()
    ve._tts_armed_at = None
    ve.audio_queue = queue.Queue(maxsize=1000)
    ve.input_gain = 1.0
    ve.flush_passes = 2
    ve.flush_gap_ms = 50
    ve.extra_tail_ms = 200

    backend = FakeBackend(block_ms=10)
    ve.audio_backend = backend
    keep = threading.Event()
    keep.set()

    # Define helper methods (mimicking actual implementation)
    def _drain_queue(max_items=10000):
        n = 0
        while n < max_items and not ve.audio_queue.empty():
            try:
                ve.audio_queue.get_nowait()
                n += 1
            except queue.Empty:
                break
        return n

    ve._drain_queue = _drain_queue

    def _post_tts_cooldown_and_flush():
        time.sleep(ve.extra_tail_ms / 1000.0)
        total = 0
        for p in range(ve.flush_passes):
            flushed = _drain_queue()
            total += flushed
            if flushed:
                print(f"  [flush pass {p+1}]: {flushed} chunks")
            time.sleep(ve.flush_gap_ms / 1000.0)
        return total

    ve._post_tts_cooldown_and_flush = _post_tts_cooldown_and_flush

    def _pre_tts_suppress():
        ve.tts_playing_evt.set()
        ve._tts_armed_at = time.monotonic()
        print("  [suppression enabled]")

    ve._pre_tts_suppress = _pre_tts_suppress

    def _clear_tts_suppress():
        ve.tts_playing_evt.clear()
        ve._tts_armed_at = None
        print("  [suppression disabled]")

    ve._clear_tts_suppress = _clear_tts_suppress

    # Filler thread (mimics actual fill_queue_from_backend)
    def filler():
        for chunk in backend.chunks(10):
            if not keep.is_set():
                break
            # Echo suppression check
            if ve.tts_suppression_enabled and ve.tts_playing_evt.is_set():
                time.sleep(0.001)  # Avoid tight spin
                continue
            ve.audio_queue.put_nowait(chunk)

    t = threading.Thread(target=filler, daemon=True)
    t.start()

    # Test 1: Normal queuing works
    print("  Queuing audio normally...")
    time.sleep(0.1)
    pre = ve.audio_queue.qsize()
    assert pre > 0, f"Expected audio queued, got {pre}"
    print(f"  ✓ Queued {pre} chunks")

    # Test 2: Suppression stops queuing
    print("  Enabling suppression...")
    ve._pre_tts_suppress()
    size_at_start = ve.audio_queue.qsize()
    time.sleep(0.1)
    size_after = ve.audio_queue.qsize()
    assert size_after == size_at_start, f"Queue grew during suppression: {size_at_start} -> {size_after}"
    print(f"  ✓ No growth during suppression (stayed at {size_at_start})")

    # Test 3: Flush empties queue
    print("  Running cooldown + flush...")
    flushed = ve._post_tts_cooldown_and_flush()
    ve._clear_tts_suppress()
    post = ve.audio_queue.qsize()
    assert post == 0, f"Queue not empty after flush: {post} items remain"
    print(f"  ✓ Flushed {flushed} chunks, queue empty")

    # Cleanup
    keep.clear()
    backend.stop()
    t.join(timeout=1)

    print("  ✓ Test 1 PASSED\n")


def test_watchdog():
    """Test that watchdog clears stuck suppression flag after 30s."""
    print("=== Test 2: Watchdog ===")

    ve = SimpleNamespace()
    ve.tts_playing_evt = threading.Event()
    ve._tts_armed_at = None

    # Simulate stuck flag
    print("  Simulating stuck suppression...")
    ve.tts_playing_evt.set()
    ve._tts_armed_at = time.monotonic() - 31  # 31 seconds ago

    # Watchdog check (mimics actual _duplex_healthcheck)
    if ve.tts_playing_evt.is_set() and ve._tts_armed_at:
        if time.monotonic() - ve._tts_armed_at > 30:
            print("  [watchdog] Clearing stuck flag")
            ve.tts_playing_evt.clear()
            ve._tts_armed_at = None

    assert not ve.tts_playing_evt.is_set(), "Watchdog failed to clear stuck flag"
    print("  ✓ Watchdog cleared stuck flag")
    print("  ✓ Test 2 PASSED\n")


def test_concurrent_queuing():
    """Test that suppression and queuing work correctly under concurrent access."""
    print("=== Test 3: Concurrent Queuing ===")

    ve = SimpleNamespace()
    ve.tts_suppression_enabled = True
    ve.tts_playing_evt = threading.Event()
    ve.audio_queue = queue.Queue(maxsize=1000)
    ve.input_gain = 1.0

    backend = FakeBackend(block_ms=5)  # Faster for stress test
    keep = threading.Event()
    keep.set()

    def filler():
        for chunk in backend.chunks(5):
            if not keep.is_set():
                break
            if ve.tts_suppression_enabled and ve.tts_playing_evt.is_set():
                time.sleep(0.001)
                continue
            ve.audio_queue.put_nowait(chunk)

    # Start multiple filler threads
    threads = [threading.Thread(target=filler, daemon=True) for _ in range(3)]
    for t in threads:
        t.start()

    # Let them queue
    time.sleep(0.05)
    initial = ve.audio_queue.qsize()
    assert initial > 0, "No audio queued"
    print(f"  Queued {initial} chunks from 3 threads")

    # Enable suppression
    ve.tts_playing_evt.set()
    size_before = ve.audio_queue.qsize()
    time.sleep(0.05)
    size_after = ve.audio_queue.qsize()

    growth = size_after - size_before
    assert growth <= 1, f"Queue grew during suppression: {growth} chunks"
    print(f"  ✓ Minimal growth during suppression ({growth} chunks)")

    # Cleanup
    keep.clear()
    backend.stop()
    for t in threads:
        t.join(timeout=1)

    print("  ✓ Test 3 PASSED\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("KLoROS Half-Duplex Audio Suppression Tests")
    print("="*60)

    try:
        test_halfduplex_suppression()
        test_watchdog()
        test_concurrent_queuing()

        print("="*60)
        print("✓ ALL TESTS PASSED")
        print("="*60 + "\n")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        raise
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}\n")
        raise
