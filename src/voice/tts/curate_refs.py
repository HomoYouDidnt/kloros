"""Voice reference curation for XTTS voice cloning."""
import os, glob, json, soundfile as sf, numpy as np, librosa

def speech_ms(pcm, sr, vad_aggr=2, frame_ms=20, max_gap_ms=500):
    """Calculate milliseconds of speech in audio.

    Args:
        pcm: Audio PCM data
        sr: Sample rate
        vad_aggr: VAD aggressiveness (0-3)
        frame_ms: Frame size in milliseconds
        max_gap_ms: Maximum gap to bridge

    Returns:
        Milliseconds of speech
    """
    from src.compat import webrtcvad
    vad = webrtcvad.Vad(int(vad_aggr))
    frame = int(sr * frame_ms / 1000)
    speech = np.zeros(len(pcm), dtype=bool)

    for i in range(0, len(pcm) - frame + 1, frame):
        ok = vad.is_speech((pcm[i:i+frame] * 32768).astype(np.int16).tobytes(), sr)
        if ok:
            speech[i:i+frame] = True

    # Bridge small gaps
    gap = int(sr * max_gap_ms / 1000)
    i = 0
    while i < len(speech):
        if not speech[i]:
            j = i
            while j < len(speech) and not speech[j]:
                j += 1
            if (j - i) <= gap:
                speech[i:j] = True
            i = j
        else:
            i += 1

    return int(1000 * speech.sum() / sr)

def normalize(pcm):
    """Normalize audio to -1 to 1 range."""
    m = np.max(np.abs(pcm)) + 1e-6
    return (pcm / m).astype(np.float32)

def curate(in_glob, out_dir, target_sr=22050, min_speech_ms=2500, max_clips=120):
    """Curate voice references from audio files.

    Args:
        in_glob: Glob pattern for input audio files
        out_dir: Output directory for curated references
        target_sr: Target sample rate
        min_speech_ms: Minimum speech duration in milliseconds
        max_clips: Maximum number of clips to select

    Returns:
        List of selected file paths
    """
    paths = sorted(glob.glob(os.path.expanduser(in_glob), recursive=True))
    os.makedirs(os.path.expanduser(out_dir), exist_ok=True)
    picked = []

    for p in paths:
        try:
            pcm, sr = sf.read(p, always_2d=False)
            if pcm.ndim > 1:
                pcm = pcm.mean(axis=1)

            if sr != target_sr:
                pcm = librosa.resample(pcm.astype('float32'), orig_sr=sr, target_sr=target_sr)
                sr = target_sr

            pcm = normalize(pcm)

            if speech_ms(pcm, sr) < min_speech_ms:
                continue

            # Trim silence
            pcm, _ = librosa.effects.trim(pcm, top_db=24)

            if len(pcm) / sr < 2.0:
                continue

            name = os.path.basename(p)
            outp = os.path.join(
                os.path.expanduser(out_dir),
                name if name.endswith(".wav") else name + ".wav"
            )
            sf.write(outp, pcm, sr)
            picked.append(outp)

            if len(picked) >= max_clips:
                break
        except Exception:
            continue

    # Write manifest
    with open(os.path.join(os.path.expanduser(out_dir), "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"refs": picked}, f, indent=2)

    return picked

def make_dream_job(out_dir, dataset_glob, target_sr=22050, min_speech_ms=2500, max_clips=120):
    """Create a D-REAM job spec for TTS reference building.

    Args:
        out_dir: Output directory for job spec
        dataset_glob: Glob pattern for dataset
        target_sr: Target sample rate
        min_speech_ms: Minimum speech duration
        max_clips: Maximum clips

    Returns:
        Job specification dict
    """
    job = {
        "job_type": "tts_reference_build",
        "dataset_glob": dataset_glob,
        "curation_params": {
            "target_sr": target_sr,
            "min_speech_ms": min_speech_ms,
            "max_clips": max_clips
        },
        "fitness": {
            "metrics": ["wer_proxy", "speaker_similarity", "latency_first_audio_ms"],
            "goal": "maximize_stability_and_clarity"
        },
        "output_dir": out_dir
    }

    os.makedirs(os.path.expanduser(out_dir), exist_ok=True)
    with open(os.path.join(os.path.expanduser(out_dir), "job_spec.json"), "w", encoding="utf-8") as f:
        json.dump(job, f, indent=2)

    return job

if __name__ == "__main__":
    import argparse, yaml
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config/tts.yaml")
    ap.add_argument("--emit-job", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(os.path.expanduser(args.cfg), "r", encoding="utf-8"))
    out_dir = cfg["xtts_v2"]["refs_dir"]
    ds = cfg["dream_jobs"]["dataset_glob"]
    targ = int(cfg["dream_jobs"]["target_sr"])
    ms = int(cfg["dream_jobs"]["min_speech_ms"])
    k = int(cfg["dream_jobs"]["max_clips"])

    curate(ds, out_dir, targ, ms, k)

    if args.emit_job:
        make_dream_job(cfg["dream_jobs"]["out_dir"], ds, targ, ms, k)
        print("Emitted D‑REAM job spec to", cfg["dream_jobs"]["out_dir"])
