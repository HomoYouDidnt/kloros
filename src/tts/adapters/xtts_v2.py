import os, glob, numpy as np
from typing import Iterable

class XTTSBackend:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._playing = False
        self._tts = None
        self._refs = None
        self.sr = int(cfg.get("audio", {}).get("sample_rate", 22050))

    def _load(self):
        if self._tts:
            return
        from TTS.api import TTS
        model = self.cfg.get("xtts_v2", {}).get("model", "tts_models/multilingual/multi-dataset/xtts_v2")
        device = self.cfg.get("xtts_v2", {}).get("device", "cpu")
        self._tts = TTS(model).to(device)
        refs_dir = os.path.expanduser(self.cfg.get("xtts_v2", {}).get("refs_dir", "~/KLoROS/voice_refs/active"))
        if os.path.isdir(refs_dir):
            self._refs = sorted(glob.glob(os.path.join(refs_dir, "*.wav")))[:32] or None

    def start(self):
        self._load()
        self._playing = True

    def stream_text(self, chunks: Iterable[str]):
        speed = float(self.cfg.get("xtts_v2", {}).get("speed", 1.0))
        language = self.cfg.get("xtts_v2", {}).get("language", "en")
        for text in chunks:
            if not self._playing:
                break
            wav = self._tts.tts(text=text, speaker_wav=self._refs, speed=speed, language=language)
            yield (np.array(wav, dtype=np.float32).clip(-1, 1) * 32767.0).astype("int16").tobytes()

    def stop(self):
        self._playing = False

    def is_playing(self):
        return self._playing

    def prewarm(self):
        """Prewarm the model for faster first synthesis."""
        self._load()
