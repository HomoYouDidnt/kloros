# Changelog

## Unreleased

- docs: add README with device helper and env var documentation
- feat: add `--list-devices` helper to `src/kloros_voice.py` to list audio devices and suggest `KLR_INPUT_IDX`
- fix: make runtime Linux-first and add platform guards for `pactl`/`aplay` (Windows devs will skip those calls)
- fix: defensive Vosk model loading and guards so missing models don't crash dev machines
- test: make `src/test_components.py` cross-platform and defensive when tools/models are missing
