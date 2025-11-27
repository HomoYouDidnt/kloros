"""
Wiki indexer for KLoROS codebase.

Scans the src directory for Python files, groups them into logical modules,
computes SHA-256 hashes of concatenated file contents, and generates an index.json
file that tracks module metadata.
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set


class WikiIndexer:
    """Indexes Python modules in the codebase and generates a module index."""

    def __init__(self, src_dir: str, wiki_dir: str):
        """Initialize the indexer.

        Args:
            src_dir: Path to the source directory to index
            wiki_dir: Path to the wiki directory where index.json is stored
        """
        self.src_dir = Path(src_dir)
        self.wiki_dir = Path(wiki_dir)
        self.index_path = self.wiki_dir / "index.json"

    def find_python_files(self) -> Dict[str, List[Path]]:
        """Recursively find all Python files and group them by module.

        Returns:
            Dictionary mapping module_id to list of file paths
        """
        modules: Dict[str, List[Path]] = {}

        for py_file in self.src_dir.rglob("*.py"):
            if "__pycache__" in py_file.parts or ".egg-info" in py_file.parts:
                continue

            rel_path = py_file.relative_to(self.src_dir)
            parts = rel_path.parts[:-1]

            if not parts:
                module_id = "root"
            else:
                module_id = ".".join(parts)

            if module_id not in modules:
                modules[module_id] = []

            modules[module_id].append(py_file)

        return modules

    def compute_hash(self, file_paths: List[Path]) -> str:
        """Compute SHA-256 hash of concatenated file contents.

        Args:
            file_paths: List of file paths to hash

        Returns:
            SHA-256 hash as "sha256:..." string
        """
        hasher = hashlib.sha256()

        for file_path in sorted(file_paths):
            try:
                with open(file_path, "rb") as f:
                    hasher.update(f.read())
            except (IOError, OSError) as e:
                raise RuntimeError(f"Failed to read {file_path}: {e}")

        return f"sha256:{hasher.hexdigest()}"

    def load_existing_index(self) -> Dict:
        """Load the existing index.json file.

        Returns:
            Dictionary with index structure or empty template if file doesn't exist
        """
        if self.index_path.exists():
            try:
                with open(self.index_path, "r") as f:
                    return json.load(f)
            except (IOError, json.JSONDecodeError):
                return self._create_empty_index()
        return self._create_empty_index()

    def _create_empty_index(self) -> Dict:
        """Create an empty index template."""
        return {
            "version": 1,
            "generated_ts": 0.0,
            "modules": {}
        }

    def build_index(self) -> Dict:
        """Build the module index.

        Returns:
            Dictionary with the generated index structure
        """
        modules = self.find_python_files()
        existing_index = self.load_existing_index()
        current_ts = datetime.now().timestamp()

        new_modules = {}

        for module_id, file_paths in sorted(modules.items()):
            code_paths = [str(p.relative_to(self.src_dir)) for p in sorted(file_paths)]
            current_hash = self.compute_hash(file_paths)

            existing_module = existing_index.get("modules", {}).get(module_id, {})

            new_modules[module_id] = {
                "module_id": module_id,
                "code_paths": code_paths,
                "current_hash": current_hash,
                "last_seen_ts": current_ts,
                "wiki_hash": existing_module.get("wiki_hash"),
                "wiki_status": existing_module.get("wiki_status", "missing"),
                "capabilities": existing_module.get("capabilities", []),
                "zooids": existing_module.get("zooids", []),
                "pipelines": existing_module.get("pipelines", [])
            }

        return {
            "version": 1,
            "generated_ts": current_ts,
            "modules": new_modules
        }

    def save_index(self, index: Dict) -> None:
        """Save the index to index.json.

        Args:
            index: Dictionary to save as JSON
        """
        self.wiki_dir.mkdir(parents=True, exist_ok=True)

        with open(self.index_path, "w") as f:
            json.dump(index, f, indent=2)

    def run(self) -> Dict:
        """Run the indexer and save results.

        Returns:
            The generated index dictionary
        """
        index = self.build_index()
        self.save_index(index)
        return index


def main() -> None:
    """Main entry point for the wiki indexer CLI."""
    src_dir = "/home/kloros/src"
    wiki_dir = "/home/kloros/wiki"

    indexer = WikiIndexer(src_dir, wiki_dir)
    index = indexer.run()

    module_count = len(index["modules"])
    file_count = sum(len(m["code_paths"]) for m in index["modules"].values())

    print(f"Wiki indexer completed successfully")
    print(f"  Modules indexed: {module_count}")
    print(f"  Total files: {file_count}")
    print(f"  Index saved to: {wiki_dir}/index.json")


if __name__ == "__main__":
    main()
