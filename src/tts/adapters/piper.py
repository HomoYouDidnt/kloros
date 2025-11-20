import subprocess, shlex
from typing import Iterable

class PiperBackend:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._playing = False
        p = self.cfg.get("piper", {})
        self.model = p.get("model_path")
        self.len = p.get("length_scale", 1.0)
        self.ns = p.get("noise_scale", 0.67)
        self.nw = p.get("noise_w", 0.80)
        self._proc = None

    def start(self):
        self._playing = True
        # Start piper process
        cmd = [
            "piper",
            "--model", self.model,
            "--output_raw",
            "--length_scale", str(self.len),
            "--noise_scale", str(self.ns),
            "--noise_w", str(self.nw)
        ]
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def stream_text(self, chunks: Iterable[str]):
        for text in chunks:
            if not self._playing or self._proc is None:
                break
            self._proc.stdin.write((text + "\n").encode("utf-8"))
            self._proc.stdin.flush()
            # Note: This is a simplified version - real streaming would read from stdout
            yield b""
        if self._proc:
            self._proc.stdin.close()
            self._proc.wait()
            self._proc = None

    def stop(self):
        self._playing = False
        if self._proc:
            self._proc.terminate()
            self._proc.wait()
            self._proc = None

    def is_playing(self):
        return self._playing

    def prewarm(self):
        """Prewarm the backend."""
        pass
