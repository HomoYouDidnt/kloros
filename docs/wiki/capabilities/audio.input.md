---
doc_type: capability
capability_id: audio.input
status: enabled
last_updated: '2025-11-22T18:32:26.481455'
drift_status: ok
---
# audio.input

## Purpose

Provides: mic_stream, levels, vad

Kind: device
## Scope

Documentation: docs/audio.md

Tests:
- audio_probe_basic

## Implementations

No module dependencies.

Preconditions:
- group:audio
- path:/dev/snd readable
- pipewire_session

## Telemetry

Health check: `bash:pactl list short sources | grep -v monitor | grep -q .`

Cost:
- CPU: 1
- Memory: 64 MB
- Risk: low

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
