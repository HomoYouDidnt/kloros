"""
Repository indexer: builds symbol graph and file index.

Uses:
- ripgrep for fast file search
- ctags or tree-sitter for symbol extraction
- TF-IDF for relevance ranking
"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict
import math

@dataclass
class Symbol:
    """A code symbol (function, class, method)."""
    name: str
    kind: str  # function, class, method, variable
    file: str
    line: int
    language: str

@dataclass
class FileInfo:
    """Information about a source file."""
    path: str
    size_bytes: int
    line_count: int
    symbols: List[Symbol]
    imports: List[str]

class RepoIndex:
    """Repository index with symbol and file information."""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.files: Dict[str, FileInfo] = {}
        self.symbols: Dict[str, List[Symbol]] = defaultdict(list)  # name -> [Symbol]
        self.file_symbols: Dict[str, List[Symbol]] = defaultdict(list)  # file -> [Symbol]

    def build(self, extensions: Optional[List[str]] = None):
        """
        Build the index by scanning the repository.

        Args:
            extensions: List of file extensions to index (e.g., ['.py', '.js'])
        """
        if extensions is None:
            extensions = ['.py']  # Default to Python

        # Find all source files
        source_files = self._find_source_files(extensions)

        # Extract symbols from each file
        for file_path in source_files:
            file_info = self._index_file(file_path)
            if file_info:
                self.files[str(file_path.relative_to(self.repo_root))] = file_info

                # Index symbols by name
                for symbol in file_info.symbols:
                    self.symbols[symbol.name].append(symbol)
                    self.file_symbols[file_info.path].append(symbol)

    def _find_source_files(self, extensions: List[str]) -> List[Path]:
        """Find all source files with given extensions."""
        files = []

        for ext in extensions:
            pattern = f"**/*{ext}"
            for path in self.repo_root.rglob(pattern):
                # Skip common ignore patterns
                if any(part.startswith('.') or part in ['__pycache__', 'node_modules', 'venv', '.venv']
                       for part in path.parts):
                    continue
                if path.is_file():
                    files.append(path)

        return files

    def _index_file(self, file_path: Path) -> Optional[FileInfo]:
        """Index a single file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.splitlines()

            symbols = self._extract_symbols_python(file_path, content)
            imports = self._extract_imports_python(content)

            rel_path = str(file_path.relative_to(self.repo_root))

            return FileInfo(
                path=rel_path,
                size_bytes=file_path.stat().st_size,
                line_count=len(lines),
                symbols=symbols,
                imports=imports
            )

        except Exception as e:
            print(f"Error indexing {file_path}: {e}")
            return None

    def _extract_symbols_python(self, file_path: Path, content: str) -> List[Symbol]:
        """Extract Python symbols using simple regex parsing."""
        import re

        symbols = []
        rel_path = str(file_path.relative_to(self.repo_root))

        # Find classes
        for match in re.finditer(r'^class\s+(\w+)', content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            symbols.append(Symbol(
                name=match.group(1),
                kind='class',
                file=rel_path,
                line=line_num,
                language='python'
            ))

        # Find functions/methods
        for match in re.finditer(r'^(?:async\s+)?def\s+(\w+)', content, re.MULTILINE):
            line_num = content[:match.start()].count('\n') + 1
            symbols.append(Symbol(
                name=match.group(1),
                kind='function',
                file=rel_path,
                line=line_num,
                language='python'
            ))

        return symbols

    def _extract_imports_python(self, content: str) -> List[str]:
        """Extract Python imports."""
        import re

        imports = []

        # from X import Y
        for match in re.finditer(r'^from\s+([\w.]+)\s+import', content, re.MULTILINE):
            imports.append(match.group(1))

        # import X
        for match in re.finditer(r'^import\s+([\w.]+)', content, re.MULTILINE):
            imports.append(match.group(1))

        return imports

    def find_symbol(self, name: str) -> List[Symbol]:
        """Find all symbols with given name."""
        return self.symbols.get(name, [])

    def find_symbols_in_file(self, file_path: str) -> List[Symbol]:
        """Find all symbols in a file."""
        return self.file_symbols.get(file_path, [])

    def save(self, output_path: Path):
        """Save index to JSON file."""
        data = {
            "repo_root": str(self.repo_root),
            "files": {path: asdict(info) for path, info in self.files.items()},
            "symbol_count": len(self.symbols),
            "file_count": len(self.files)
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, index_path: Path) -> 'RepoIndex':
        """Load index from JSON file."""
        with open(index_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        index = cls(Path(data["repo_root"]))

        for path, file_data in data["files"].items():
            symbols = [Symbol(**s) for s in file_data["symbols"]]
            file_info = FileInfo(
                path=file_data["path"],
                size_bytes=file_data["size_bytes"],
                line_count=file_data["line_count"],
                symbols=symbols,
                imports=file_data["imports"]
            )

            index.files[path] = file_info

            for symbol in symbols:
                index.symbols[symbol.name].append(symbol)
                index.file_symbols[path].append(symbol)

        return index


class ContextPacker:
    """Pack relevant context for a coding task."""

    def __init__(self, index: RepoIndex):
        self.index = index
        self.tfidf_cache = self._compute_tfidf()

    def _compute_tfidf(self) -> Dict[str, Dict[str, float]]:
        """Compute TF-IDF scores for symbols across files."""
        # Count how many files each symbol appears in
        doc_freq = defaultdict(int)
        for symbol_name in self.index.symbols:
            files = set(s.file for s in self.index.symbols[symbol_name])
            doc_freq[symbol_name] = len(files)

        total_docs = len(self.index.files)

        # Compute IDF
        idf = {}
        for symbol, df in doc_freq.items():
            idf[symbol] = math.log(total_docs / (1 + df))

        # Compute TF-IDF per file
        tfidf = {}
        for file_path, file_info in self.index.files.items():
            tfidf[file_path] = {}
            symbol_counts = defaultdict(int)
            for symbol in file_info.symbols:
                symbol_counts[symbol.name] += 1

            for symbol, count in symbol_counts.items():
                tf = count / max(len(file_info.symbols), 1)
                tfidf[file_path][symbol] = tf * idf.get(symbol, 0)

        return tfidf

    def get_relevant_files(
        self,
        query_symbols: List[str],
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Get most relevant files for given symbols.

        Args:
            query_symbols: List of symbol names to search for
            top_k: Number of files to return

        Returns:
            List of (file_path, relevance_score) tuples
        """
        file_scores = defaultdict(float)

        for query_symbol in query_symbols:
            # Direct matches
            for symbol in self.index.find_symbol(query_symbol):
                file_scores[symbol.file] += 2.0  # Boost for exact match

            # TF-IDF based relevance
            for file_path, symbol_scores in self.tfidf_cache.items():
                if query_symbol in symbol_scores:
                    file_scores[file_path] += symbol_scores[query_symbol]

        # Sort by score
        ranked = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    def pack_context(
        self,
        task_description: str,
        failing_tests: Optional[List[str]] = None,
        max_files: int = 5,
        lines_per_file: int = 200
    ) -> Dict[str, str]:
        """
        Pack relevant context for a task.

        Args:
            task_description: Description of the task
            failing_tests: List of failing test names
            max_files: Maximum files to include
            lines_per_file: Maximum lines per file

        Returns:
            Dict mapping file_path -> relevant snippet
        """
        # Extract potential symbols from task description
        import re
        words = re.findall(r'\b[a-z_][a-z0-9_]{2,}\b', task_description.lower())

        # Get relevant files
        relevant_files = self.get_relevant_files(words, top_k=max_files)

        context = {}
        for file_path, score in relevant_files:
            file_info = self.index.files.get(file_path)
            if file_info:
                # Read file and extract relevant lines
                full_path = self.index.repo_root / file_path
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()

                    # Include full file if small, otherwise take symbols + context
                    if len(lines) <= lines_per_file:
                        context[file_path] = ''.join(lines)
                    else:
                        # Extract lines around symbols
                        relevant_lines = set()
                        for symbol in file_info.symbols:
                            if any(word in symbol.name.lower() for word in words):
                                # Include symbol + 5 lines context
                                for i in range(max(0, symbol.line - 5),
                                             min(len(lines), symbol.line + 10)):
                                    relevant_lines.add(i)

                        if relevant_lines:
                            snippet_lines = sorted(relevant_lines)[:lines_per_file]
                            context[file_path] = ''.join(lines[i] for i in snippet_lines)

                except Exception as e:
                    print(f"Error reading {file_path}: {e}")

        return context
