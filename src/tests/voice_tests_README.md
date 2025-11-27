# Voice Zooid Test Suite

Comprehensive test suite for the three extracted voice zooids: Audio I/O, STT, and TTS.

## Test Architecture

This test suite follows a 3-layer testing pyramid:

```
                   E2E Tests (minimal)
                  /                 \
           Integration Tests
          /                     \
    Unit Tests (comprehensive)
```

### Layer 1: Unit Tests (Fast, Isolated)

Tests each zooid in isolation with mocked UMN and dependencies.

- **Location**: `tests/unit/`
- **Runtime**: <1s per test
- **Coverage**: Core zooid functionality without external dependencies

#### Files:
- `test_voice_audio_io.py` - Audio I/O zooid unit tests
  - Initialization and configuration
  - Audio capture start/stop
  - Audio playback (mocked paplay)
  - WAV file saving
  - UMN signal emission
  - Shutdown behavior

- `test_voice_stt.py` - STT zooid unit tests
  - Initialization and backend selection
  - Audio file loading
  - Transcription (mocked backend)
  - Statistics tracking
  - UMN signal emission
  - Error handling

- `test_voice_tts.py` - TTS zooid unit tests
  - Initialization and backend selection
  - Text synthesis (mocked backend)
  - Text normalization (KLoROS pronunciation)
  - Affective state handling
  - Fail-open mode
  - Statistics tracking

**Run unit tests only:**
```bash
pytest tests/unit/test_voice_*.py -v
```

### Layer 2: Integration Tests (Real UMN, No Mocks)

Tests zooid pairs communicating via real UMN pub/sub.

- **Location**: `tests/integration/`
- **Runtime**: <5s per test
- **Coverage**: Signal coordination and event propagation

#### Files:
- `test_voice_orchestrator_stt.py` - Orchestrator → STT integration
  - VOICE.AUDIO.CAPTURED → VOICE.STT.TRANSCRIPTION flow
  - VOICE.STT.READY signal emission
  - incident_id correlation
  - Multiple transcriptions

- `test_voice_orchestrator_tts.py` - Orchestrator → TTS integration
  - VOICE.ORCHESTRATOR.SPEAK → VOICE.TTS.AUDIO.READY flow
  - VOICE.ORCHESTRATOR.SPEAK → VOICE.TTS.PLAY.AUDIO flow
  - VOICE.TTS.READY signal emission
  - incident_id correlation
  - Urgency propagation
  - Multiple speak requests

- `test_voice_tts_audio_io.py` - TTS → Audio I/O integration
  - VOICE.TTS.PLAY.AUDIO → VOICE.AUDIO.PLAYBACK.COMPLETE flow
  - VOICE.AUDIO.IO.READY signal emission
  - incident_id correlation
  - Error handling (missing files)
  - Multiple playback requests

**Run integration tests only:**
```bash
pytest tests/integration/test_voice_*.py -v -m integration
```

### Layer 3: E2E Tests (Full System, Minimal)

Tests complete voice interaction flows with all zooids running.

- **Location**: `tests/e2e/`
- **Runtime**: Variable (depends on real audio processing)
- **Coverage**: Full conversation loop validation

#### Files:
- `test_voice_full_loop.py` - Complete voice loop E2E tests
  - Full loop: Audio Capture → STT → Orchestrator → TTS → Playback
  - All zooids READY signal emission
  - Multi-zooid coordination

**Run E2E tests only:**
```bash
pytest tests/e2e/test_voice_*.py -v -m e2e
```

## Test Fixtures

### Audio Fixtures
Location: `tests/fixtures/`

Generated test audio files:
- `test_audio_1s.wav` - 1 second sine wave (440 Hz)
- `test_audio_short.wav` - 0.3 second sine wave
- `test_audio_silent.wav` - 0.5 second silence

Generate fixtures manually:
```bash
python3 tests/fixtures/generate_test_audio.py
```

### UMN Mock
Location: `tests/fixtures/umn_mock.py`

Provides `MockUMNPub` and `MockUMNSub` for unit testing without real UMN.

## Running Tests

### Run all voice tests:
```bash
pytest tests/unit/test_voice_*.py tests/integration/test_voice_*.py tests/e2e/test_voice_*.py -v
```

### Run only fast tests (unit):
```bash
pytest tests/unit/test_voice_*.py -v
```

### Run with coverage:
```bash
pytest tests/unit/test_voice_*.py tests/integration/test_voice_*.py --cov=src --cov-report=html
```

### Skip slow tests:
```bash
pytest tests/ -v -m "not slow"
```

### Skip integration and E2E tests:
```bash
pytest tests/ -v -m "not integration and not e2e"
```

## Test Environment Variables

Unit tests respect these environment variables (but use mocks):
- `KLR_AUDIO_SAMPLE_RATE` - Audio sample rate (default: 16000)
- `KLR_AUDIO_RECORDINGS_DIR` - Audio recordings directory
- `KLR_ENABLE_STT` - Enable STT (0/1)
- `KLR_STT_BACKEND` - STT backend (mock/vosk/whisper/hybrid)
- `KLR_STT_LANG` - STT language (default: en-US)
- `KLR_ENABLE_TTS` - Enable TTS (0/1)
- `KLR_TTS_BACKEND` - TTS backend (mock/piper/coqui)
- `KLR_TTS_SAMPLE_RATE` - TTS sample rate (default: 22050)
- `KLR_TTS_OUT_DIR` - TTS output directory
- `KLR_FAIL_OPEN_TTS` - Fail-open mode (0/1)

## Test Design Principles

1. **Fast by default**: Unit tests run in <1s each
2. **No external dependencies**: Unit tests mock hardware/models
3. **Repeatable**: No reliance on real microphones or speakers
4. **Isolated**: Each test creates its own temporary directories
5. **Clean**: Tests clean up after themselves (temp files, processes)
6. **Documented**: Each test has clear docstrings explaining what it validates

## Coverage Goals

- **Unit Tests**: 80%+ line coverage per zooid
- **Integration Tests**: All UMN signal flows validated
- **E2E Tests**: Basic conversation loop validated

## Known Limitations

1. Unit tests mock audio backends - real audio I/O tested separately
2. Integration tests may require UMN proxy to be running
3. E2E tests are minimal - comprehensive testing at unit/integration layers
4. GPU-dependent features (Whisper, TTS) use mock backends in tests

## Adding New Tests

### Unit Test Template:
```python
def test_new_feature(self, zooid):
    """Test description."""
    # Arrange
    zooid.start()

    # Act
    result = zooid.some_method()

    # Assert
    assert result is not None
    assert zooid.chem_pub.get_signal_count("SOME.SIGNAL") == 1
```

### Integration Test Template:
```python
@pytest.mark.integration
def test_new_signal_flow(self, monkeypatch):
    """Test signal flow between zooids."""
    received_signal = threading.Event()
    signal_data = {}

    def on_signal(msg):
        signal_data.update(msg.get("facts", {}))
        received_signal.set()

    # Subscribe to signal
    sub = UMNSub("SIGNAL.NAME", on_signal, ...)

    # Start zooid
    zooid = SomeZooid()
    zooid.start()

    try:
        # Emit trigger signal
        pub = UMNPub()
        pub.emit("TRIGGER.SIGNAL", ...)

        # Wait for response
        success = received_signal.wait(timeout=5.0)
        assert success

        # Validate signal data
        assert signal_data["key"] == "value"
    finally:
        sub.close()
        pub.close()
        zooid.shutdown()
```

## Troubleshooting

### Tests fail with "UMN connection refused"
- Ensure UMN proxy is running for integration tests
- Check `XPUB_ENDPOINT` and `XSUB_ENDPOINT` environment variables

### Tests hang waiting for signals
- Increase timeout values in `wait()` calls
- Check that zooids are actually started before emitting signals
- Verify signal names match exactly (case-sensitive)

### Audio fixture generation fails
- Ensure NumPy is installed: `pip install numpy`
- Check write permissions to `tests/fixtures/` directory

### Mock backend not working
- Verify `patch` decorators target correct import paths
- Check that mock is applied before zooid initialization
