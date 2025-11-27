import pytest
from pathlib import Path
from src.core.model_manager import ModelManager, ModelInfo


@pytest.fixture
def temp_model_dir(tmp_path):
    """Create temporary model directory."""
    return str(tmp_path / "models")


def test_model_manager_init(temp_model_dir):
    """Test ModelManager initialization creates directory."""
    manager = ModelManager(model_dir=temp_model_dir)
    assert Path(temp_model_dir).exists()
    assert manager.model_dir == Path(temp_model_dir)


def test_list_models_empty(temp_model_dir):
    """Test listing models when none are downloaded."""
    manager = ModelManager(model_dir=temp_model_dir)
    models = manager.list_models()

    assert len(models) > 0
    assert all(not m["downloaded"] for m in models)
    assert all(m["path"] is None for m in models)


def test_get_model_path_not_exists(temp_model_dir):
    """Test getting path for non-existent model."""
    manager = ModelManager(model_dir=temp_model_dir)
    path = manager.get_model_path("qwen2.5:7b")
    assert path is None


def test_get_model_path_exists(temp_model_dir):
    """Test getting path for existing model."""
    manager = ModelManager(model_dir=temp_model_dir)

    Path(temp_model_dir).mkdir(parents=True, exist_ok=True)
    dummy_file = Path(temp_model_dir) / "qwen2.5-7b-instruct-q3_k_m.gguf"
    dummy_file.write_text("dummy")

    path = manager.get_model_path("qwen2.5:7b")
    assert path == dummy_file
    assert path.exists()


def test_get_model_info(temp_model_dir):
    """Test retrieving model metadata."""
    manager = ModelManager(model_dir=temp_model_dir)
    info = manager.get_model_info("qwen2.5:7b")

    assert info is not None
    assert isinstance(info, ModelInfo)
    assert info.name == "qwen2.5:7b"
    assert info.size_gb > 0
    assert info.min_vram_gb > 0


def test_get_model_info_unknown(temp_model_dir):
    """Test retrieving info for unknown model."""
    manager = ModelManager(model_dir=temp_model_dir)
    info = manager.get_model_info("nonexistent-model")
    assert info is None
