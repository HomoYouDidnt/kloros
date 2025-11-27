# Changelog

## v1.1.0 - 2025-09-22 - Stability & Quality Release

### Code Quality & CI Improvements
- fix: resolve all Ruff lint errors (13 issues) - import formatting, unused imports, variable naming
- fix: apply Ruff code formatting to ensure consistent style across all speaker recognition modules
- fix: resolve Bandit security warnings by adding `usedforsecurity=False` to test MD5 usage
- fix: resolve MyPy type checking error in embedding backend (numpy float conversion)
- feat: complete CI pipeline compliance - all lint, format, security, and type checks passing

### Production & Deployment Optimizations
- chore: optimize KLoROS for Linux production deployment with 60-70% file reduction
- docs: add comprehensive Linux installation checklist and validation guide
- chore: remove development artifacts, cache directories, and unnecessary documentation
- feat: streamlined production-ready installation preserving all core functionality

### Quality Assurance
- ✅ All automated quality checks now passing
- ✅ Complete speaker recognition system validation
- ✅ Production-ready Linux deployment optimization
- ✅ Security compliance and type safety verified

## v1.0.0 - 2025-09-22 - Voice Identification System

### Major Features
- **feat: Complete voice identification system with speaker recognition**
- feat: Voice enrollment with 5 KLoROS-branded sentences and name verification
- feat: Automatic speaker identification after wake word detection for personalized interactions
- feat: Multi-backend architecture (mock for testing, embedding for production)
- feat: Voice commands: "enroll me", "list users", "delete user [name]", "cancel"
- feat: Seamless integration with existing voice loop and audio capture
- feat: Environment configuration via KLR_ENABLE_SPEAKER_ID, KLR_SPEAKER_BACKEND, KLR_SPEAKER_THRESHOLD

### Technical Implementation
- feat: Protocol-based speaker backend architecture following KLoROS patterns
- feat: Name verification system with spell-out confirmation
- feat: KLoROS-branded enrollment sentences including signature "What fragile crisis needs fixing today?"
- feat: Complete test suite with 4/4 tests passing and comprehensive validation script
- feat: Full documentation and troubleshooting guide (SPEAKER_RECOGNITION.md)
- feat: Privacy-focused local storage of voice embeddings

### Development & Testing
- feat: Mock backend with pre-populated test users (alice, bob, charlie)
- feat: Embedding backend using sentence-transformers for production use
- feat: Comprehensive test suite (test_speaker_system.py) with full validation
- feat: Graceful fallbacks when speaker recognition is disabled or unavailable

## Previous Releases

### Foundation Features
- docs: add README with device helper and env var documentation
- feat: add `--list-devices` helper to `src/kloros_voice.py` to list audio devices and suggest `KLR_INPUT_IDX`
- fix: make runtime Linux-first and add platform guards for `pactl`/`aplay` (Windows devs will skip those calls)
- fix: defensive Vosk model loading and guards so missing models don't crash dev machines
- test: make `src/test_components.py` cross-platform and defensive when tools/models are missing
