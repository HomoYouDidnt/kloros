---
doc_type: capability
capability_id: audio.output
status: enabled
last_updated: '2025-11-22T18:32:26.481800'
drift_status: ok
---
# audio.output

## Purpose

Provides: tts_playback, beep, audio_feedback

Kind: device
## Scope

Documentation: docs/audio.md

Tests:
- audio_playback_test

## Implementations

No module dependencies.

Preconditions:
- group:audio
- path:/dev/snd readable
- pipewire_session

## Telemetry

Health check: `pactl list short sinks`

Cost:
- CPU: 1
- Memory: 64 MB
- Risk: low

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
