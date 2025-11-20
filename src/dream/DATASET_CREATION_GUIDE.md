# ASR Evaluation Dataset Creation Guide

**Purpose**: Create proper evaluation datasets for D-REAM optimization testing

**Current Issue**: Using 3-sample `mini_eval_set` → all scores identical
**Solution**: Create 50-100 sample dataset → meaningful score variation

---

## Quick Start: Generate Dataset Now

### Option 1: Use Automated Script (Recommended)

```bash
# Generate 50-sample dataset using TTS
cd /home/kloros
sudo -u kloros /home/kloros/.venv/bin/python3 /home/kloros/src/tools/generate_eval_dataset.py \
  --output /home/kloros/assets/asr_eval/large_eval_set \
  --samples 50

# Wait ~5-10 minutes for generation to complete
```

### Option 2: Quick Test with Existing Audio

```bash
# Copy and duplicate existing samples
sudo -u kloros mkdir -p /home/kloros/assets/asr_eval/test_eval_set
cd /home/kloros/assets/asr_eval/mini_eval_set

# Duplicate samples 20 times
for i in {1..20}; do
  for sample in sample*.wav; do
    base=$(basename $sample .wav)
    cp ${base}.wav ../test_eval_set/${base}_copy${i}.wav
    cp ${base}.txt ../test_eval_set/${base}_copy${i}.txt
    cp ${base}.vad.json ../test_eval_set/${base}_copy${i}.vad.json
  done
done

# Now you have 60 samples (3 original × 20 copies)
```

---

## Dataset Requirements

### File Structure

Each sample needs **3 files**:

```
dataset_directory/
├── sample001.wav          # Audio file (16kHz, mono recommended)
├── sample001.txt          # Ground truth transcription
├── sample001.vad.json     # VAD annotations (optional, can be generated)
├── sample002.wav
├── sample002.txt
├── sample002.vad.json
...
```

### File Formats

**1. Audio (.wav)**:
- Format: 16-bit PCM WAV
- Sample rate: 16000 Hz (recommended)
- Channels: 1 (mono)
- Duration: 1-30 seconds typical

**2. Transcription (.txt)**:
- Plain text file
- Exact transcription of audio
- Lowercase, no punctuation (for WER calculation)
- Example: `hello world`

**3. VAD Annotations (.vad.json)**:
```json
{
  "sample_rate": 16000,
  "segments_ms": [
    {
      "start": 50,
      "end": 1125
    }
  ]
}
```

---

## Method 1: Synthetic Generation (Fastest)

**Pros**: Fast, consistent, known ground truth
**Cons**: Less realistic than human speech

### Using the Automated Script

```bash
# Generate 50 samples
sudo -u kloros /home/kloros/.venv/bin/python3 /home/kloros/src/tools/generate_eval_dataset.py \
  --samples 50 \
  --output /home/kloros/assets/asr_eval/large_eval_set

# Or with custom sentences
echo "your custom sentence here
another sentence here
third sentence here" > /tmp/custom_sentences.txt

sudo -u kloros /home/kloros/.venv/bin/python3 /home/kloros/src/tools/generate_eval_dataset.py \
  --custom-sentences /tmp/custom_sentences.txt \
  --output /home/kloros/assets/asr_eval/custom_eval_set
```

### Manual TTS Generation

```bash
# Create directory
sudo -u kloros mkdir -p /home/kloros/assets/asr_eval/manual_eval_set
cd /home/kloros/assets/asr_eval/manual_eval_set

# Generate audio for each sentence
echo "the quick brown fox jumps over the lazy dog" | piper \
  --model /home/kloros/models/piper/glados_piper_medium.onnx \
  --output_file sample001.wav

# Save transcription
echo "the quick brown fox jumps over the lazy dog" > sample001.txt

# Generate VAD (using Python)
python3 << 'EOF'
import torch
import torchaudio
import json

model, utils = torch.hub.load('snakers4/silero-vad', 'silero_vad')
(get_speech_timestamps, _, _, _, _) = utils

wav, sr = torchaudio.load('sample001.wav')
timestamps = get_speech_timestamps(wav, model, sampling_rate=sr)

segments = [{"start": int(t['start']/sr*1000), "end": int(t['end']/sr*1000)} for t in timestamps]

with open('sample001.vad.json', 'w') as f:
    json.dump({"sample_rate": sr, "segments_ms": segments}, f, indent=2)
EOF
```

---

## Method 2: Public Datasets (Most Realistic)

**Pros**: Real human speech, diverse accents, production-quality
**Cons**: Larger download, more setup

### LibriSpeech (Recommended)

```bash
# Download LibriSpeech test-clean (2.5 GB)
cd /home/kloros/assets/asr_eval/
wget http://www.openslr.org/resources/12/test-clean.tar.gz
tar -xzf test-clean.tar.gz

# Convert to D-REAM format
sudo -u kloros python3 << 'EOF'
import os
from pathlib import Path
import shutil

librispeech_dir = Path("/home/kloros/assets/asr_eval/LibriSpeech/test-clean")
output_dir = Path("/home/kloros/assets/asr_eval/librispeech_eval_set")
output_dir.mkdir(exist_ok=True)

sample_num = 1
for flac_file in list(librispeech_dir.rglob("*.flac"))[:50]:  # Take first 50
    txt_file = flac_file.with_suffix(".txt")

    # Convert FLAC to WAV
    wav_file = output_dir / f"sample{sample_num:03d}.wav"
    os.system(f"ffmpeg -i {flac_file} -ar 16000 -ac 1 {wav_file} -y 2>/dev/null")

    # Copy transcription
    with open(txt_file) as f:
        text = f.read().lower().strip()
    with open(output_dir / f"sample{sample_num:03d}.txt", 'w') as f:
        f.write(text)

    sample_num += 1

print(f"Created {sample_num-1} samples in {output_dir}")
EOF

# Generate VAD for all samples
# (Use script from Method 1)
```

### Mozilla Common Voice

```bash
# Download Common Voice dataset
# https://commonvoice.mozilla.org/en/datasets

# Extract 50 samples and convert to D-REAM format
# Similar process as LibriSpeech above
```

---

## Method 3: Record Custom Audio

**Pros**: Domain-specific, custom vocabulary
**Cons**: Time-consuming, requires recording setup

```bash
# Record using arecord (Linux)
arecord -f S16_LE -r 16000 -c 1 -d 5 sample001.wav

# Or use Python
python3 << 'EOF'
import sounddevice as sd
import soundfile as sf

duration = 5  # seconds
sample_rate = 16000

print("Recording...")
audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
sd.wait()

sf.write('sample001.wav', audio, sample_rate)
print("Saved to sample001.wav")
EOF

# Manually transcribe
echo "your spoken text here" > sample001.txt

# Generate VAD (see Method 1)
```

---

## Testing Your Dataset

### 1. Quick Validation

```bash
# Check files
ls -lh /home/kloros/assets/asr_eval/large_eval_set/*.wav | wc -l  # Should match sample count
ls -lh /home/kloros/assets/asr_eval/large_eval_set/*.txt | wc -l
ls -lh /home/kloros/assets/asr_eval/large_eval_set/*.vad.json | wc -l

# Sample a few transcriptions
head -5 /home/kloros/assets/asr_eval/large_eval_set/sample001.txt
head -5 /home/kloros/assets/asr_eval/large_eval_set/sample025.txt
```

### 2. Run Quick Benchmark

```bash
# Test with new dataset
sudo -u kloros bash -c 'export DREAM_ARTIFACTS=/home/kloros/src/dream/artifacts && \
  export PYTHONPATH=/home/kloros:$PYTHONPATH && \
  /opt/kloros/tools/stt_bench '"'"'{"dataset_path":"/home/kloros/assets/asr_eval/large_eval_set","beam":3}'"'"

# Check results
cat /home/kloros/src/phase/phase_report.jsonl | tail -1 | python3 -m json.tool
```

### 3. Run D-REAM Optimization

```bash
# Now run GA search with proper dataset
sudo -u kloros bash -c 'export DREAM_ARTIFACTS=/home/kloros/src/dream/artifacts && \
  export PYTHONPATH=/home/kloros:$PYTHONPATH && \
  /opt/kloros/tools/dream/run_hp_search '"'"'{"domain":"asr_tts","generations":10,"population_size":6}'"'"' \
  > /home/kloros/logs/large_dataset_hp_search.log 2>&1 &'

# Monitor progress
tail -f /home/kloros/logs/large_dataset_hp_search.log
```

---

## Expected Results with Proper Dataset

### With 3 samples (current):
```
All scores: 0.85 (identical)
No variation to optimize
```

### With 50+ samples (proper dataset):
```
Score range: 0.72 - 0.91
Clear winners and losers
Meaningful optimization possible
```

### Example Dashboard Comparison:
```
Run A (optimized): Score 0.91, WER 0.12, Latency 140ms
Baseline:          Score 0.85, WER 0.25, Latency 180ms
Delta:             +0.06 score, -0.13 WER, -40ms latency ← HUGE IMPROVEMENT!
```

---

## Recommended Next Steps

**For immediate testing** (fastest):
```bash
# Generate 50 synthetic samples (~10 minutes)
sudo -u kloros /home/kloros/.venv/bin/python3 /home/kloros/src/tools/generate_eval_dataset.py \
  --samples 50 \
  --output /home/kloros/assets/asr_eval/large_eval_set
```

**For production use** (best quality):
```bash
# Download LibriSpeech test-clean
# Convert first 100 samples to D-REAM format
# Use for all future optimization runs
```

**For domain-specific** (custom application):
```bash
# Record 50-100 samples in your domain
# Add custom vocabulary and phrases
# Best accuracy for your specific use case
```

---

## Troubleshooting

### Issue: "piper: command not found"
```bash
# Install Piper TTS
pip install piper-tts
# Or check installation path
which piper
```

### Issue: "torch.hub.load failed"
```bash
# Clear torch cache
rm -rf /home/kloros/.cache/torch/hub/
# Re-run script
```

### Issue: "Permission denied"
```bash
# Fix ownership
sudo chown -R kloros:kloros /home/kloros/assets/asr_eval/
```

---

## Summary

**Minimum recommended**: 50 samples
**Good for testing**: 100 samples
**Production quality**: 500+ samples

**Time estimates**:
- Synthetic generation: ~10 minutes for 50 samples
- LibriSpeech download: ~30 minutes
- Manual recording: ~5-10 hours for 50 samples

**Once dataset is ready**, D-REAM optimization will show:
- Real score variation (0.70 - 0.92 range)
- Meaningful improvements (+0.05 to +0.15 score deltas)
- Dashboard comparison feature shines with color-coded improvements!
