import subprocess, shlex, soundfile as sf, io, numpy as np, librosa
from typing import Iterable

class Mimic3Backend:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._playing = False
        self.voice = cfg.get("mimic3", {}).get("voice", "en_US/vctk_low")
        self.sr = int(cfg.get("audio", {}).get("sample_rate", 22050))

    def start(self):
        self._playing = True

    def stream_text(self, chunks: Iterable[str]):
        # Find mimic3 in PATH or venv
        import shutil
        mimic3_path = shutil.which("mimic3") or "/home/kloros/.venv/bin/mimic3"

        for text in chunks:
            if not self._playing:
                break
            cmd = f"{mimic3_path} --voice {shlex.quote(self.voice)} {shlex.quote(text)} --stdout"
            p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            data = p.stdout.read()
            p.wait()
            pcm, sr = sf.read(io.BytesIO(data), always_2d=False)
            if sr != self.sr:
                pcm = librosa.resample(pcm.astype('float32'), orig_sr=sr, target_sr=self.sr)
                sr = self.sr
            if pcm.ndim > 1:
                pcm = pcm.mean(axis=1)
            yield (pcm.clip(-1, 1) * 32767.0).astype('int16').tobytes()

    def stop(self):
        self._playing = False

    def is_playing(self):
        return self._playing

    def prewarm(self):
        """Prewarm the backend."""
        pass
