"""E2E scenario tests for KLoROS text and audio interface."""
from pathlib import Path
import tempfile

import pytest

from harness.logs import wait_for_final_response
from harness.scenario import load_scenario
from harness.text_ingress import send_text_prompt
from harness.audio import text_to_wav, send_audio_prompt, verify_tts_output_exists
from harness.bus import get_monitor

SCEN_DIR = Path(__file__).parents[1] / "scenarios"


@pytest.mark.parametrize("scenario_path", sorted(SCEN_DIR.glob("*.yaml")))
def test_scenario(scenario_path):
    """
    Run E2E scenario test with text or audio interface.

    Drives KLoROS via text or audio prompt depending on scenario mode:
    - text (default): HTTP text ingress
    - audio: Synthesize audio, send via HTTP audio ingress, verify TTS output

    Validates:
    - Final response logged correctly
    - Response contains expected phrases
    - Metrics within expected bounds
    - Artifacts created if specified
    - TTS output generated (audio mode only)
    """
    s = load_scenario(scenario_path)
    print(f"\n[test] Running scenario: {s.name}")

    mode = getattr(s, 'mode', 'text')  # Default to text mode
    print(f"[test] Mode: {mode}")

    # Phase 3: Start MQTT monitor if events are expected
    mqtt_monitor = None
    if s.events:
        mqtt_monitor = get_monitor()
        if not mqtt_monitor.running:
            mqtt_monitor.start()
        mqtt_monitor.clear_events()
        print(f"[test] MQTT monitor started for {len(s.events)} expected events")

    # Drive KLoROS via text or audio
    for step in s.steps:
        prompt = step["say"]
        print(f"[test] Sending prompt: {prompt}")

        if mode == "audio":
            # Phase 2: Audio ingress
            # 1. Synthesize text to audio
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                audio_path = Path(tmp.name)

            text_to_wav(prompt, audio_path)
            print(f"[test] Synthesized audio: {audio_path}")

            # 2. Send audio to ingress
            result = send_audio_prompt(audio_path)
            print(f"[test] Audio ingress result: {result.get('ok')}")

            # Cleanup temp file
            audio_path.unlink()

        else:
            # Phase 1: Text ingress
            send_text_prompt(prompt)

    # Observe final response in logs
    print(f"[test] Waiting for final_response log entry...")
    final = wait_for_final_response(timeout_s=15)
    assert final, "No final_response log line observed"

    print(f"[test] Final response: {final.get('final_text', '')[:100]}...")

    # Oracles: speech text contains (if final_text is logged)
    if s.speech_contains and "final_text" in final:
        text = final.get("final_text", "").lower()
        for phrase in s.speech_contains:
            assert phrase.lower() in text, f"Missing phrase: '{phrase}' in response"
            print(f"[test] ✓ Found phrase: '{phrase}'")

    # Metrics: latency/tool_calls
    m = s.metrics or {}
    if "latency_ms_max" in m:
        latency = int(final.get("latency_ms", 999999))
        max_latency = m["latency_ms_max"]
        assert latency <= max_latency, f"Latency {latency}ms > max {max_latency}ms"
        print(f"[test] ✓ Latency: {latency}ms <= {max_latency}ms")

    if "tool_calls_max" in m:
        tool_calls = int(final.get("tool_calls", 999999))
        max_tools = m["tool_calls_max"]
        assert tool_calls <= max_tools, f"Tool calls {tool_calls} > max {max_tools}"
        print(f"[test] ✓ Tool calls: {tool_calls} <= {max_tools}")

    # Phase 2: TTS output verification
    if mode == "audio" and hasattr(s, 'tts_output') and s.tts_output:
        assert verify_tts_output_exists(), "TTS output not found at ~/.kloros/tts/last.wav"
        print(f"[test] ✓ TTS output generated")

    # Artifacts: optional file checks
    for a in s.artifacts:
        p = Path(a["path"]).expanduser()
        assert p.exists(), f"Missing artifact: {p}"
        print(f"[test] ✓ Found artifact: {p}")

        content = p.read_text(encoding="utf-8", errors="ignore")
        for needle in a.get("contains", []):
            assert needle.lower() in content.lower(), f"Artifact missing '{needle}'"
            print(f"[test] ✓ Artifact contains: '{needle}'")

    # Phase 3: Event bus validation
    if s.events and mqtt_monitor:
        print(f"[test] Validating {len(s.events)} MQTT events...")
        for event_expectation in s.events:
            topic = event_expectation["topic"]
            print(f"[test] Waiting for event: {topic}")

            # Wait for the event
            event = mqtt_monitor.wait_for_event(topic, timeout_s=5.0)
            assert event, f"Missing event: {topic}"
            print(f"[test] ✓ Received event: {topic}")

            # Validate payload contents
            if "payload_contains" in event_expectation:
                for key, expected_value in event_expectation["payload_contains"].items():
                    if key.endswith("_min"):
                        # Handle minimum value checks (e.g., tool_calls_min)
                        field_name = key[:-4]  # Remove "_min" suffix
                        actual_value = event["payload"].get(field_name, 0)
                        assert actual_value >= expected_value, f"Event {topic}: {field_name}={actual_value} < {expected_value}"
                        print(f"[test] ✓ Event payload: {field_name}={actual_value} >= {expected_value}")
                    else:
                        # Handle exact/contains checks
                        actual_value = event["payload"].get(key, "")
                        if isinstance(expected_value, str):
                            assert expected_value.lower() in str(actual_value).lower(), f"Event {topic}: '{expected_value}' not in {key}"
                            print(f"[test] ✓ Event payload contains: {key}='{expected_value}'")
                        else:
                            assert actual_value == expected_value, f"Event {topic}: {key}={actual_value} != {expected_value}"
                            print(f"[test] ✓ Event payload: {key}={actual_value}")

    print(f"[test] ✅ Scenario passed: {s.name}")
