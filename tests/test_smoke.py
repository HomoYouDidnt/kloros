import os
import subprocess


def test_ollama_call(monkeypatch):
    class DummyResp:
        status_code = 200

        def json(self):
            return {"response": "Hello from Ollama"}

    def fake_post(_url, json, timeout=None):
        assert "model" in json
        _ = timeout
        return DummyResp()

    monkeypatch.setattr("requests.post", fake_post)

    # Import and call KLoROS.chat minimal flow
    from src.kloros_voice import KLoROS

    k = KLoROS()
    # Bypass model dependency for this test
    k.vosk_model = None
    resp = k.chat("Hello")
    assert "Hello from Ollama" in resp


def test_piper_run(monkeypatch, tmp_path):
    # Mock subprocess.run to avoid calling system piper/aplay
    calls = []

    def fake_run(cmd, input=None, capture_output=False, check=False, timeout=None):
        _ = timeout
        calls.append(cmd)

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)

    from src.kloros_voice import KLoROS

    k = KLoROS()
    # point to a non-existent but harmless piper path via env override
    os.environ["KLR_PIPER_EXE"] = "/usr/bin/piper"
    # create a fake piper model path
    k.piper_model = str(tmp_path / "dummy.onnx")
    with open(k.piper_model, "wb") as f:
        f.write(b"0")

    # Should not raise
    k.speak("Testing")
    assert any("piper" in str(c) for c in calls)
