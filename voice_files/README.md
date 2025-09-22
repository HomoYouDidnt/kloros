# Voice Files Directory

This directory contains all audio samples that KLoROS uses for voice processing and that metadata from ~/rag_data references.

## Directory Structure

- **system/** - KLoROS system audio files (beeps, tones, alerts, UI sounds)
- **samples/** - General voice samples and audio examples
- **training/** - Training data for voice models and recognition systems
- **user_voices/** - Speaker enrollment recordings and user voice profiles
- **reference/** - Reference audio files for testing and calibration

## File Organization Guidelines

- Place system-generated audio (alerts, beeps) in `system/`
- Put example voice clips and demonstrations in `samples/`
- Store training data for ML models in `training/`
- Keep user enrollment recordings in `user_voices/`
- Use `reference/` for test files and audio standards

## Note

The necessary files are located on the source machine and will be transferred appropriately once the system framework is deployed post testing.