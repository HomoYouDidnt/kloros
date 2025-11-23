# Voice Zooid Tests - Quick Start Guide

## 1. Run Unit Tests (Fast - Recommended First)

```bash
cd /home/kloros/.worktrees/voice-refactor-phase0
./tests/run_voice_tests.sh unit
```

Expected output: 55 tests pass in <30 seconds

## 2. Run Integration Tests (Requires ChemBus)

```bash
./tests/run_voice_tests.sh integration
```

Expected output: 17 tests pass in <60 seconds

## 3. Run E2E Tests (Full System)

```bash
./tests/run_voice_tests.sh e2e
```

Expected output: 3 tests pass in <30 seconds

## 4. Run All Tests

```bash
./tests/run_voice_tests.sh all
```

Expected output: 75 tests pass in <2 minutes

## 5. Generate Coverage Report

```bash
./tests/run_voice_tests.sh coverage
```

Opens coverage report in: `coverage_voice_zooids/index.html`

## Test Markers

Skip slow tests:
```bash
pytest tests/ -m "not slow"
```

Run only integration tests:
```bash
pytest tests/ -m integration
```

Run only unit tests (no ChemBus required):
```bash
pytest tests/unit/test_voice*.py
```

## Troubleshooting

### "ChemBus connection refused"
- Integration tests require ChemBus proxy
- Check if ChemBus is running: `systemctl status kloros-chem-proxy`
- Or skip integration tests: `./tests/run_voice_tests.sh unit`

### "ImportError: No module named X"
- Install dependencies: `pip install pytest numpy`
- Or use project venv: `source venv/bin/activate`

### Tests hang
- Increase timeout in test files (default: 5 seconds)
- Check that ChemBus proxy is responsive

### Audio fixture missing
- Generate fixtures: `python3 tests/fixtures/generate_test_audio.py`

## Quick Test Examples

### Test a single zooid:
```bash
pytest tests/unit/test_voice_stt.py -v
```

### Test a specific function:
```bash
pytest tests/unit/test_voice_stt.py::TestSTTTranscription::test_transcribe_audio_success -v
```

### Run with verbose output:
```bash
pytest tests/unit/test_voice*.py -vv
```

## Next Steps

See `voice_tests_README.md` for comprehensive documentation.
