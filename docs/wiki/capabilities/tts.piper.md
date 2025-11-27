---
doc_type: capability
capability_id: tts.piper
status: enabled
last_updated: '2025-11-22T18:32:26.482966'
drift_status: ok
---
# tts.piper

## Purpose

Provides: text_to_speech, voice_synthesis

Kind: service
## Scope

Documentation: docs/tts.md

Tests:
- tts_synthesis_test

## Implementations

No module dependencies.

Preconditions:
- path:/home/kloros/models/piper/glados_piper_medium.onnx readable
- command:piper available
- audio.output:ok

## Telemetry

Health check: `command:which piper`

Cost:
- CPU: 20
- Memory: 256 MB
- Risk: low

## Drift Status

**Status:** OK

All preconditions are satisfied. Module dependencies are available in index.
