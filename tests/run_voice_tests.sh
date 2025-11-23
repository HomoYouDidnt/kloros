#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "=== Voice Zooid Test Suite Runner ==="
echo "Project root: $PROJECT_ROOT"
echo ""

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

OPTIONS:
    unit            Run unit tests only (fast)
    integration     Run integration tests only (real ChemBus)
    e2e             Run E2E tests only (full system)
    all             Run all voice tests (default)
    coverage        Run with coverage report
    fast            Run unit tests only (alias for 'unit')
    help            Show this help message

EXAMPLES:
    $0 unit         # Run unit tests
    $0 coverage     # Run all tests with coverage
    $0 fast         # Quick unit test run

EOF
}

MODE="${1:-all}"

case "$MODE" in
    unit|fast)
        echo "Running unit tests only..."
        pytest tests/unit/test_voice_*.py -v
        ;;

    integration)
        echo "Running integration tests..."
        pytest tests/integration/test_voice_*.py -v -m integration
        ;;

    e2e)
        echo "Running E2E tests..."
        pytest tests/e2e/test_voice_*.py -v -m e2e
        ;;

    all)
        echo "Running all voice tests..."
        pytest tests/unit/test_voice_*.py \
               tests/integration/test_voice_*.py \
               tests/e2e/test_voice_*.py \
               -v
        ;;

    coverage)
        echo "Running all voice tests with coverage..."
        pytest tests/unit/test_voice_*.py \
               tests/integration/test_voice_*.py \
               tests/e2e/test_voice_*.py \
               -v \
               --cov=src/kloros_voice_audio_io \
               --cov=src/kloros_voice_stt \
               --cov=src/kloros_voice_tts \
               --cov-report=term-missing \
               --cov-report=html:coverage_voice_zooids
        echo ""
        echo "Coverage report generated in: coverage_voice_zooids/index.html"
        ;;

    help|-h|--help)
        show_help
        ;;

    *)
        echo "Unknown option: $MODE"
        echo ""
        show_help
        exit 1
        ;;
esac

echo ""
echo "=== Test run complete ==="
