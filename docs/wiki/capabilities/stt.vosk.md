---
doc_type: capability
capability_id: stt.vosk
status: enabled
last_updated: '2025-11-22T18:32:26.482739'
drift_status: missing_module
---
# stt.vosk

## Purpose

Provides: transcribe_live, speech_recognition

Kind: service
## Scope

Documentation: docs/stt.md

Tests:
- stt_transcribe_test

## Implementations

Referenced modules:

### vosk (NOT FOUND)

Preconditions:
- path:/home/kloros/models/vosk/model readable
- module:vosk importable
- audio.input:ok

## Telemetry

Health check: `python:vosk_model_loaded`

Cost:
- CPU: 15
- Memory: 512 MB
- Risk: low

## Drift Status

**Status:** MISSING_MODULE

One or more required modules are not found in the index.

Details:
- Module 'vosk' referenced but not found in index

