# KLoROS E2E Test Harness - Phase 1 (Text-Only)

Black-box end-to-end tests for KLoROS using text-only interface.

## What This Does

- Sends text prompts to KLoROS HTTP endpoint (no audio yet)
- Monitors `~/.kloros/logs/kloros-YYYYMMDD.jsonl` for final response
- Validates response content, latency, and tool call metrics
- Optional: Checks for artifact files (ACE bullets export, etc.)

## Prerequisites

1. **KLoROS running** with text ingress endpoint
2. **Structured logging** enabled with `phase="final_response"` entries
3. **Python 3.10+**

## Setup

```bash
cd kloros-e2e
python -m venv .venv
source .venv/bin/activate  # or: .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

## Configuration

Edit `tests/harness.toml` to match your setup:

```toml
ingress_http_url = "http://127.0.0.1:8124/ingest-text"
structured_log_glob = "~/.kloros/logs/kloros-*.jsonl"
```

## Running Tests

### 1. Start KLoROS HTTP Text Ingress

In a separate terminal:

```bash
cd /home/kloros
source .venv/bin/activate
python -m ingress.http_text
```

This starts the FastAPI endpoint on `http://127.0.0.1:8124`.

### 2. Run E2E Tests

```bash
pytest -v
```

Or run a specific scenario:

```bash
pytest tests/e2e/test_scenarios.py::test_scenario_text_only[system_diagnostic.yaml] -v
```

## Test Scenarios

Current scenarios (aligned with existing KLoROS tools):

- **system_diagnostic.yaml** - Calls `system_diagnostic` tool
- **check_recent_errors.yaml** - Calls `check_recent_errors` tool
- **memory_status.yaml** - Checks memory system status
- **audio_status.yaml** - Checks audio pipeline status

## Adding New Scenarios

Create a YAML file in `tests/scenarios/`:

```yaml
name: "My test scenario"
steps:
  - say: "Run my command"

expect:
  speech_contains:
    - "expected phrase"
    - "another phrase"
  metrics:
    latency_ms_max: 5000
    tool_calls_max: 4
  artifacts:  # Optional
    - path: "~/.kloros/out/my_file.md"
      contains:
        - "expected content"
```

## Troubleshooting

### No final_response log found

- Check that KLoROS is logging to `~/.kloros/logs/`
- Verify `phase="final_response"` is in the log entries
- Check `harness.toml` log glob pattern

### HTTP connection errors

- Ensure `ingress/http_text.py` is running
- Check port 8124 is not already in use
- Verify firewall isn't blocking localhost:8124

### Latency/tool call assertions fail

- Adjust `metrics.latency_ms_max` in scenario YAML
- Check KLoROS performance (LLM speed, tool complexity)
- Review tool call count in final_response log

## Next Steps: Phase 2

To enable full audio testing:

1. Add `/ingest-audio` endpoint for WAV file ingestion
2. Write last TTS output to `~/.kloros/tts/last.wav`
3. Update harness to synthesize audio prompts
4. Enable speech probe for TTS verification

## Next Steps: Phase 3

To add event bus monitoring:

1. Add MQTT client to KLoROS
2. Publish events: `kloros/turn/completed`, etc.
3. Enable `bus.py` probe in harness
4. Add event expectations to scenarios
