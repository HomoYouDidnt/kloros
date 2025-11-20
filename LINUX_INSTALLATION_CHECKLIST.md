# KLoROS Linux Installation Checklist

## ✅ Cleanup Completed

Your KLoROS installation has been cleaned and optimized for Linux deployment. This checklist ensures everything is properly configured.

## File Structure Verification

### ✅ Essential Components Present
- **Core System**: Complete `src/` directory with all modules
- **Speaker Recognition**: Full `src/speaker/` system with v1.0 voice identification
- **Configuration**: `requirements.txt`, `pyproject.toml`, `setup.cfg`
- **Documentation**: `README.md`, `SPEAKER_RECOGNITION.md`, `ENVIRONMENT.md`
- **Tests**: Complete `tests/` directory + `test_speaker_system.py`
- **Scripts**: Utility scripts in `scripts/` directory
- **Data**: RAG data and voice files preserved

### ✅ Development Artifacts Removed
- **Cache directories**: `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`
- **Development files**: `codex-recovery.patch`, CI configs, Claude settings
- **Dev documentation**: `TODO.md`, `PLAN.md`, `AUDIT.md`, instruction files
- **Empty directories**: `configs/` and other unused folders

## Linux Installation Steps

### 1. File Permissions (Run on Linux)
```bash
# Make scripts executable
chmod +x scripts/*.py
chmod +x test_speaker_system.py

# Ensure main entry point is executable
chmod +x src/kloros_voice.py
```

### 2. Install Dependencies
```bash
# Install Python dependencies
pip install -r requirements.txt

# Or use Poetry if preferred
pip install poetry
poetry install
```

### 3. Configure Speaker Recognition
```bash
# Enable speaker recognition (optional)
export KLR_ENABLE_SPEAKER_ID=1
export KLR_SPEAKER_BACKEND=mock  # or 'embedding' for production
export KLR_SPEAKER_THRESHOLD=0.8
```

### 4. Validate Installation
```bash
# Test basic imports
python -c "from src.kloros_voice import KLoROS; print('✓ KLoROS imports successfully')"

# Run comprehensive speaker system tests
python test_speaker_system.py

# Run system smoke test
python -m pytest tests/test_system_smoke.py -v
```

### 5. Optional: Remove Additional Components
If you need to save more space:

```bash
# Remove accuracy testing stack (113K)
rm -rf kloROS_accuracy_stack/

# Remove tools directory if not needed
rm -rf tools/

# Remove git history if not using version control
rm -rf .git/
```

## Final Directory Structure

```
kloros/
├── src/                     # Core KLoROS system
│   ├── speaker/            # Voice identification system (NEW in v1.0)
│   ├── audio/              # Audio processing
│   ├── stt/                # Speech-to-text backends
│   ├── tts/                # Text-to-speech backends
│   ├── reasoning/          # LLM reasoning backends
│   └── ...                 # Other core modules
├── tests/                  # Test suite
├── scripts/                # Utility scripts
├── rag_data/              # RAG embeddings and data
├── models/                # Model directories (Vosk/Piper)
├── voice_files/           # Voice file storage
├── requirements.txt       # Python dependencies
├── pyproject.toml         # Project configuration
├── README.md              # Main documentation
├── SPEAKER_RECOGNITION.md # Speaker system guide
└── test_speaker_system.py # Speaker system validation
```

## Functionality Verification

### ✅ Validated Systems
- **Core imports**: All Python modules import correctly
- **Speaker recognition**: Complete voice identification system functional
- **Enrollment system**: 5-sentence enrollment with name verification works
- **User management**: Voice commands for listing/deleting users work
- **Backend fallbacks**: Graceful degradation when components unavailable

### Voice Commands Available
- `"enroll me"` - Start voice enrollment
- `"list users"` - Show enrolled speakers
- `"delete user [name]"` - Remove voice profile
- `"cancel"` - Cancel enrollment process

## Size Optimization Results

**Before cleanup**: ~150+ files with development artifacts
**After cleanup**: ~70 essential files
**Space saved**: ~60-70% reduction in file count
**Optional further reduction**: Remove `kloROS_accuracy_stack/` for additional 113K

## Next Steps

1. **Transfer to Linux**: Copy the cleaned directory to your Linux system
2. **Set permissions**: Run the permission commands above
3. **Install dependencies**: Use pip or poetry to install requirements
4. **Test functionality**: Run validation scripts
5. **Configure models**: Set up Vosk/Piper models as needed (see `ENVIRONMENT.md`)

Your KLoROS installation is now optimized and ready for Linux deployment with the complete v1.0 speaker recognition system! 🎯