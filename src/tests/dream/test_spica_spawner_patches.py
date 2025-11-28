import pytest
import shutil
from pathlib import Path
from src.dream.config_tuning.spica_spawner import apply_code_patch, run_tests_in_instance


@pytest.fixture
def mock_instance(tmp_path):
    instance_dir = tmp_path / "spica-test"
    instance_dir.mkdir()

    src_dir = instance_dir / "src" / "test"
    src_dir.mkdir(parents=True)

    test_file = src_dir / "example.py"
    test_file.write_text("def old_function():\n    return 'old'\n")

    return instance_dir


def test_apply_code_patch_success(mock_instance):
    target_file = Path("src/test/example.py")
    patch_content = "def new_function():\n    return 'new'\n"

    result = apply_code_patch(
        instance_dir=mock_instance,
        target_file=target_file,
        patch_content=patch_content
    )

    assert result is True
    patched_file = mock_instance / target_file
    assert patched_file.read_text() == patch_content


def test_apply_code_patch_creates_dirs(mock_instance):
    target_file = Path("src/new_module/file.py")
    patch_content = "# new module\n"

    result = apply_code_patch(
        instance_dir=mock_instance,
        target_file=target_file,
        patch_content=patch_content
    )

    assert result is True
    patched_file = mock_instance / target_file
    assert patched_file.exists()
    assert patched_file.read_text() == patch_content


def test_apply_code_patch_invalid_path(mock_instance):
    target_file = Path("../../../etc/passwd")
    patch_content = "malicious"

    result = apply_code_patch(
        instance_dir=mock_instance,
        target_file=target_file,
        patch_content=patch_content
    )

    assert result is False


def test_run_tests_in_instance(mock_instance):
    result = run_tests_in_instance(
        instance_dir=mock_instance,
        test_command="echo 'test passed'"
    )

    assert result["success"] is True
    assert "test passed" in result["output"]


def test_run_tests_in_instance_failure(mock_instance):
    result = run_tests_in_instance(
        instance_dir=mock_instance,
        test_command="exit 1"
    )

    assert result["success"] is False
