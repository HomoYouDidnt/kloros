from pathlib import Path
from typing import Optional, Dict, Any
import requests
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """Information about a GGUF model."""
    name: str
    filename: str
    url: str
    size_gb: float
    min_vram_gb: int
    description: str


class ModelManager:
    """
    Manages GGUF model files for llama.cpp.
    Replaces Ollama's model management functionality.
    """

    MODEL_REGISTRY = {
        "qwen2.5:7b": ModelInfo(
            name="qwen2.5:7b",
            filename="qwen2.5-7b-instruct-q3_k_m.gguf",
            url="https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q3_k_m.gguf",
            size_gb=3.81,
            min_vram_gb=5,
            description="Qwen 2.5 7B Instruct (Q3_K_M quantization)"
        ),
        "qwen2.5-coder:7b": ModelInfo(
            name="qwen2.5-coder:7b",
            filename="qwen2.5-coder-7b-instruct-q4_k_m.gguf",
            url="https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf",
            size_gb=4.68,
            min_vram_gb=6,
            description="Qwen 2.5 Coder 7B (Q4_K_M quantization)"
        ),
        "deepseek-r1:7b": ModelInfo(
            name="deepseek-r1:7b",
            filename="DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
            url="https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
            size_gb=4.68,
            min_vram_gb=6,
            description="DeepSeek R1 Distill Qwen 7B (Q4_K_M quantization)"
        ),
    }

    def __init__(self, model_dir: str = "/home/kloros/models/gguf"):
        """Initialize model manager with storage directory."""
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[ModelManager] Initialized with model_dir={self.model_dir}")

    def get_model_path(self, model_name: str) -> Optional[Path]:
        """Get local path for model. Returns None if not exists or unknown."""
        if model_name not in self.MODEL_REGISTRY:
            logger.error(f"[ModelManager] Unknown model: {model_name}")
            return None

        model_info = self.MODEL_REGISTRY[model_name]
        model_path = self.model_dir / model_info.filename

        if model_path.exists():
            return model_path

        logger.warning(f"[ModelManager] Model not found: {model_path}")
        return None

    def list_models(self) -> list[Dict[str, Any]]:
        """List available models with download status."""
        models = []
        for name, info in self.MODEL_REGISTRY.items():
            model_path = self.model_dir / info.filename
            models.append({
                "name": name,
                "filename": info.filename,
                "size_gb": info.size_gb,
                "min_vram_gb": info.min_vram_gb,
                "description": info.description,
                "downloaded": model_path.exists(),
                "path": str(model_path) if model_path.exists() else None
            })
        return models

    def download_model(self, model_name: str, force: bool = False) -> bool:
        """Download model from HuggingFace. Returns True if successful."""
        if model_name not in self.MODEL_REGISTRY:
            logger.error(f"[ModelManager] Unknown model: {model_name}")
            return False

        model_info = self.MODEL_REGISTRY[model_name]
        model_path = self.model_dir / model_info.filename

        if model_path.exists() and not force:
            logger.info(f"[ModelManager] Model already exists: {model_path}")
            return True

        logger.info(f"[ModelManager] Downloading {model_name} ({model_info.size_gb}GB)...")

        try:
            with requests.get(model_info.url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))

                with open(model_path, 'wb') as f:
                    downloaded = 0
                    chunk_size = 8192

                    for chunk in r.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            if downloaded % (100 * 1024 * 1024) < chunk_size:
                                progress_pct = (downloaded / total_size * 100) if total_size > 0 else 0
                                logger.info(f"[ModelManager] Progress: {progress_pct:.1f}%")

            logger.info(f"[ModelManager] Download complete: {model_path}")
            return True

        except Exception as e:
            logger.error(f"[ModelManager] Download failed: {e}")
            if model_path.exists():
                model_path.unlink()
            return False

    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """Get model information from registry."""
        return self.MODEL_REGISTRY.get(model_name)
