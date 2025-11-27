"""Tests for the wiki indexer module."""

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from .wiki_indexer import WikiIndexer


def test_compute_hash_single_file():
    """Test hash computation for a single file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        test_file = src_dir / "test.py"
        test_file.write_text("print(\"hello\")")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))
        hash_val = indexer.compute_hash([test_file])

        assert hash_val.startswith("sha256:")
        assert len(hash_val) == 71


def test_compute_hash_multiple_files():
    """Test hash computation for multiple files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        file1 = src_dir / "file1.py"
        file2 = src_dir / "file2.py"
        file1.write_text("code1")
        file2.write_text("code2")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))
        hash_val = indexer.compute_hash([file1, file2])

        assert hash_val.startswith("sha256:")
        assert len(hash_val) == 71


def test_compute_hash_deterministic():
    """Test that hash computation is deterministic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        test_file = src_dir / "test.py"
        test_file.write_text("consistent content")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))
        hash1 = indexer.compute_hash([test_file])
        hash2 = indexer.compute_hash([test_file])

        assert hash1 == hash2


def test_find_python_files_single_level():
    """Test finding Python files in a single directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        (src_dir / "file1.py").write_text("code")
        (src_dir / "file2.py").write_text("code")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))
        modules = indexer.find_python_files()

        assert "root" in modules
        assert len(modules["root"]) == 2


def test_find_python_files_nested():
    """Test finding Python files in nested directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        mod_dir = src_dir / "mymodule" / "submodule"
        mod_dir.mkdir(parents=True)
        (mod_dir / "file.py").write_text("code")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))
        modules = indexer.find_python_files()

        assert "mymodule.submodule" in modules
        assert len(modules["mymodule.submodule"]) == 1


def test_find_python_files_excludes_pycache():
    """Test that __pycache__ directories are excluded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        (src_dir / "real.py").write_text("code")
        pycache = src_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "cached.py").write_text("should not be found")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))
        modules = indexer.find_python_files()

        assert "root" in modules
        assert len(modules["root"]) == 1


def test_find_python_files_excludes_egg_info():
    """Test that .egg-info directories are excluded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        (src_dir / "real.py").write_text("code")
        egg_dir = src_dir / "kloros.egg-info"
        egg_dir.mkdir()
        (egg_dir / "setup.py").write_text("should not be found")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))
        modules = indexer.find_python_files()

        assert "root" in modules
        assert len(modules["root"]) == 1


def test_build_index_structure():
    """Test that build_index creates correct structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        (src_dir / "test.py").write_text("code")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))
        index = indexer.build_index()

        assert "version" in index
        assert index["version"] == 1
        assert "generated_ts" in index
        assert isinstance(index["generated_ts"], float)
        assert "modules" in index
        assert "root" in index["modules"]

        module = index["modules"]["root"]
        assert "module_id" in module
        assert module["module_id"] == "root"
        assert "code_paths" in module
        assert "current_hash" in module
        assert module["current_hash"].startswith("sha256:")
        assert "last_seen_ts" in module
        assert "wiki_hash" in module
        assert "wiki_status" in module
        assert module["wiki_status"] == "missing"
        assert "capabilities" in module
        assert "zooids" in module
        assert "pipelines" in module


def test_save_and_load_index():
    """Test saving and loading index.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        (src_dir / "test.py").write_text("code")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))
        index = indexer.build_index()
        indexer.save_index(index)

        index_file = wiki_dir / "index.json"
        assert index_file.exists()

        loaded = json.loads(index_file.read_text())
        assert loaded["version"] == 1
        assert "root" in loaded["modules"]


def test_preserves_existing_metadata():
    """Test that existing metadata is preserved across runs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        (src_dir / "test.py").write_text("code")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))

        index1 = indexer.build_index()
        indexer.save_index(index1)

        first_hash = index1["modules"]["root"]["current_hash"]
        first_wiki_hash = "sha256:existing123"

        index_data = json.loads((wiki_dir / "index.json").read_text())
        index_data["modules"]["root"]["wiki_hash"] = first_wiki_hash
        index_data["modules"]["root"]["capabilities"] = ["test_cap"]
        (wiki_dir / "index.json").write_text(json.dumps(index_data))

        index2 = indexer.build_index()

        assert index2["modules"]["root"]["wiki_hash"] == first_wiki_hash
        assert index2["modules"]["root"]["capabilities"] == ["test_cap"]


def test_run_full_workflow():
    """Test the complete indexer workflow."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "src"
        wiki_dir = Path(tmpdir) / "wiki"
        src_dir.mkdir()
        wiki_dir.mkdir()

        (src_dir / "file1.py").write_text("code1")
        subdir = src_dir / "module"
        subdir.mkdir()
        (subdir / "file2.py").write_text("code2")

        indexer = WikiIndexer(str(src_dir), str(wiki_dir))
        result = indexer.run()

        assert "root" in result["modules"]
        assert "module" in result["modules"]

        index_file = wiki_dir / "index.json"
        assert index_file.exists()

        loaded = json.loads(index_file.read_text())
        assert len(loaded["modules"]) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
