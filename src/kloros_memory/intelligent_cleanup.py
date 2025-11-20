"""
Intelligent File Cleanup for KLoROS

Enhanced housekeeping with multi-signal confidence scoring for safe,
automated file deletion. Uses multiple indicators to determine file
importance before deletion.

Safety Features:
- Multi-signal importance scoring (git, usage, dependencies, age)
- Graduated deletion (archive tier before permanent removal)
- Deletion audit trail with recovery capability
- Dry-run mode by default
- Dependency analysis for code files
"""

import os
import sys
import time
import json
import shutil
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum


class FileImportance(Enum):
    """File importance classification."""
    CRITICAL = "critical"      # Never delete (active code, configs, data)
    IMPORTANT = "important"    # Keep unless explicitly marked obsolete
    NORMAL = "normal"          # Standard retention policy
    LOW = "low"                # Candidate for early deletion
    OBSOLETE = "obsolete"      # Safe to delete


@dataclass
class FileMetrics:
    """Metrics used to assess file importance."""
    path: str
    size_bytes: int
    
    # Time metrics
    created_time: float
    modified_time: float
    accessed_time: float
    age_days: float
    days_since_access: float
    days_since_modification: float
    
    # Git metrics
    in_git: bool
    git_tracked: bool
    git_commits_count: int
    days_since_last_commit: float
    
    # Dependency metrics (for code files)
    is_python_file: bool
    imported_by_count: int
    imports_count: int
    in_systemd_service: bool
    
    # Usage metrics
    file_extension: str
    is_backup: bool
    is_temp: bool
    is_cache: bool
    
    # Importance score
    importance_score: float
    importance_class: FileImportance
    deletion_confidence: float


@dataclass
class DeletionRecord:
    """Record of file deletion for audit trail."""
    file_path: str
    deletion_time: float
    file_size: int
    file_hash: str
    importance_score: float
    deletion_reason: str
    recovery_path: Optional[str]
    metrics: Dict[str, Any]


class IntelligentCleanup:
    """
    Intelligent file cleanup with multi-signal importance analysis.
    
    Determines file importance using:
    1. Git history and tracking status
    2. File access patterns (atime, mtime)
    3. Code dependency analysis (imports)
    4. System references (systemd, cron, etc.)
    5. File type and location heuristics
    """
    
    def __init__(
        self,
        root_path: str = "/home/kloros",
        # Deletion confidence
        min_deletion_confidence: Optional[float] = None,
        # Signal weights (must sum to 1.0)
        git_weight: Optional[float] = None,
        dependency_weight: Optional[float] = None,
        usage_weight: Optional[float] = None,
        systemd_weight: Optional[float] = None,
        # Importance thresholds
        critical_threshold: Optional[float] = None,
        important_threshold: Optional[float] = None,
        normal_threshold: Optional[float] = None,
        low_threshold: Optional[float] = None,
        # Other options
        archive_before_delete: Optional[bool] = None,
        dry_run: Optional[bool] = None
    ):
        self.root_path = Path(root_path)
        self.audit_log_path = self.root_path / ".kloros" / "deletion_audit.jsonl"
        self.archive_path = self.root_path / ".kloros" / "archived_files"

        # Configuration - allow override via parameters or environment
        self.min_deletion_confidence = (
            min_deletion_confidence if min_deletion_confidence is not None
            else float(os.getenv("KLR_MIN_DELETION_CONFIDENCE", "0.85"))
        )
        self.archive_before_delete = (
            archive_before_delete if archive_before_delete is not None
            else os.getenv("KLR_ARCHIVE_BEFORE_DELETE", "1") == "1"
        )
        self.dry_run = (
            dry_run if dry_run is not None
            else os.getenv("KLR_CLEANUP_DRY_RUN", "1") == "1"
        )

        # Signal weights (default: balanced)
        self.git_weight = git_weight if git_weight is not None else 0.40
        self.dependency_weight = dependency_weight if dependency_weight is not None else 0.30
        self.usage_weight = usage_weight if usage_weight is not None else 0.20
        self.systemd_weight = systemd_weight if systemd_weight is not None else 0.10

        # Normalize weights to sum to 1.0
        total_weight = self.git_weight + self.dependency_weight + self.usage_weight + self.systemd_weight
        if total_weight > 0:
            self.git_weight /= total_weight
            self.dependency_weight /= total_weight
            self.usage_weight /= total_weight
            self.systemd_weight /= total_weight

        # Importance thresholds
        self.critical_threshold = critical_threshold if critical_threshold is not None else 0.80
        self.important_threshold = important_threshold if important_threshold is not None else 0.60
        self.normal_threshold = normal_threshold if normal_threshold is not None else 0.30
        self.low_threshold = low_threshold if low_threshold is not None else 0.15

        # Ensure directories exist
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_path.mkdir(parents=True, exist_ok=True)

        # Cache for dependency analysis
        self._import_graph: Optional[Dict[str, Set[str]]] = None
        self._systemd_references: Optional[Set[str]] = None
    
    def analyze_file(self, file_path: Path) -> FileMetrics:
        """
        Analyze a file and compute importance metrics.
        
        Returns FileMetrics with all signals and computed importance.
        """
        try:
            stat = file_path.stat()
            now = time.time()
            
            # Time metrics
            created_time = stat.st_ctime
            modified_time = stat.st_mtime
            accessed_time = stat.st_atime
            
            age_days = (now - created_time) / 86400
            days_since_modification = (now - modified_time) / 86400
            days_since_access = (now - accessed_time) / 86400
            
            # Git metrics
            git_metrics = self._get_git_metrics(file_path)
            
            # Dependency metrics (for Python files)
            dep_metrics = self._get_dependency_metrics(file_path)
            
            # File type analysis
            file_extension = file_path.suffix.lower()
            is_backup = any(pattern in file_path.name.lower() 
                          for pattern in ['.backup', 'backup-', '.bak', '~'])
            is_temp = file_path.name.startswith('.') or '/tmp/' in str(file_path)
            is_cache = '__pycache__' in str(file_path) or file_extension == '.pyc'
            
            # Compute importance score
            importance_score, importance_class = self._compute_importance(
                age_days=age_days,
                days_since_access=days_since_access,
                days_since_modification=days_since_modification,
                git_tracked=git_metrics['git_tracked'],
                git_commits=git_metrics['git_commits_count'],
                days_since_commit=git_metrics['days_since_last_commit'],
                imported_by_count=dep_metrics['imported_by_count'],
                in_systemd=dep_metrics['in_systemd_service'],
                is_backup=is_backup,
                is_temp=is_temp,
                is_cache=is_cache,
                file_extension=file_extension
            )
            
            # Deletion confidence (inverse of importance)
            deletion_confidence = self._compute_deletion_confidence(importance_score)
            
            return FileMetrics(
                path=str(file_path),
                size_bytes=stat.st_size,
                created_time=created_time,
                modified_time=modified_time,
                accessed_time=accessed_time,
                age_days=age_days,
                days_since_access=days_since_access,
                days_since_modification=days_since_modification,
                in_git=git_metrics['in_git'],
                git_tracked=git_metrics['git_tracked'],
                git_commits_count=git_metrics['git_commits_count'],
                days_since_last_commit=git_metrics['days_since_last_commit'],
                is_python_file=dep_metrics['is_python'],
                imported_by_count=dep_metrics['imported_by_count'],
                imports_count=dep_metrics['imports_count'],
                in_systemd_service=dep_metrics['in_systemd_service'],
                file_extension=file_extension,
                is_backup=is_backup,
                is_temp=is_temp,
                is_cache=is_cache,
                importance_score=importance_score,
                importance_class=importance_class,
                deletion_confidence=deletion_confidence
            )
            
        except Exception as e:
            print(f"[intelligent_cleanup] Error analyzing {file_path}: {e}")
            # Return safe default (mark as important to prevent deletion)
            return FileMetrics(
                path=str(file_path),
                size_bytes=0,
                created_time=time.time(),
                modified_time=time.time(),
                accessed_time=time.time(),
                age_days=0,
                days_since_access=0,
                days_since_modification=0,
                in_git=True,
                git_tracked=True,
                git_commits_count=999,
                days_since_last_commit=0,
                is_python_file=False,
                imported_by_count=999,
                imports_count=0,
                in_systemd_service=True,
                file_extension="",
                is_backup=False,
                is_temp=False,
                is_cache=False,
                importance_score=1.0,
                importance_class=FileImportance.CRITICAL,
                deletion_confidence=0.0
            )
    
    def _get_git_metrics(self, file_path: Path) -> Dict[str, Any]:
        """Get git-related metrics for a file."""
        metrics = {
            'in_git': False,
            'git_tracked': False,
            'git_commits_count': 0,
            'days_since_last_commit': float('inf')
        }
        
        try:
            # Check if file is in a git repo
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                cwd=file_path.parent,
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                metrics['in_git'] = True
                
                # Check if file is tracked
                result = subprocess.run(
                    ['git', 'ls-files', '--error-unmatch', file_path.name],
                    cwd=file_path.parent,
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                if result.returncode == 0:
                    metrics['git_tracked'] = True
                    
                    # Get commit count
                    result = subprocess.run(
                        ['git', 'log', '--oneline', '--', file_path.name],
                        cwd=file_path.parent,
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    
                    if result.returncode == 0:
                        metrics['git_commits_count'] = len(result.stdout.strip().split('\n'))
                        
                        # Get last commit time
                        result = subprocess.run(
                            ['git', 'log', '-1', '--format=%ct', '--', file_path.name],
                            cwd=file_path.parent,
                            capture_output=True,
                            text=True,
                            timeout=2
                        )
                        
                        if result.returncode == 0 and result.stdout.strip():
                            last_commit_time = float(result.stdout.strip())
                            metrics['days_since_last_commit'] = (time.time() - last_commit_time) / 86400
        
        except Exception:
            pass
        
        return metrics
    
    def _get_dependency_metrics(self, file_path: Path) -> Dict[str, Any]:
        """Get code dependency metrics for a file."""
        metrics = {
            'is_python': file_path.suffix == '.py',
            'imported_by_count': 0,
            'imports_count': 0,
            'in_systemd_service': False
        }
        
        if not metrics['is_python']:
            return metrics
        
        try:
            # Build import graph if not cached
            if self._import_graph is None:
                self._import_graph = self._build_import_graph()
            
            # Check how many files import this one
            module_name = self._path_to_module(file_path)
            if module_name in self._import_graph:
                metrics['imported_by_count'] = len(self._import_graph[module_name])
            
            # Count imports in this file
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                metrics['imports_count'] = content.count('import ') + content.count('from ')
            
            # Check systemd references
            if self._systemd_references is None:
                self._systemd_references = self._get_systemd_references()
            
            metrics['in_systemd_service'] = str(file_path) in self._systemd_references
            
        except Exception:
            pass
        
        return metrics
    
    def _build_import_graph(self) -> Dict[str, Set[str]]:
        """Build graph of which modules import which other modules."""
        graph = {}
        
        try:
            # Find all Python files
            python_files = list(self.root_path.rglob("*.py"))
            
            for py_file in python_files:
                try:
                    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # Extract imports (simplified)
                    imports = set()
                    for line in content.split('\n'):
                        line = line.strip()
                        if line.startswith('import ') or line.startswith('from '):
                            # Extract module name
                            if line.startswith('import '):
                                module = line.replace('import ', '').split()[0].split('.')[0]
                            else:
                                module = line.replace('from ', '').split()[0].split('.')[0]
                            imports.add(module)
                    
                    # Add to graph (reverse mapping: module -> imported by)
                    for imported_module in imports:
                        if imported_module not in graph:
                            graph[imported_module] = set()
                        graph[imported_module].add(self._path_to_module(py_file))
                
                except Exception:
                    continue
        
        except Exception:
            pass
        
        return graph
    
    def _get_systemd_references(self) -> Set[str]:
        """Get set of files referenced in systemd service files."""
        references = set()
        
        try:
            # Search systemd service files
            service_dirs = [
                Path("/etc/systemd/system"),
                Path("/home/kloros/.config/systemd/user")
            ]
            
            for service_dir in service_dirs:
                if not service_dir.exists():
                    continue
                
                for service_file in service_dir.glob("*.service"):
                    try:
                        with open(service_file, 'r') as f:
                            content = f.read()
                        
                        # Extract file paths (simplified)
                        for line in content.split('\n'):
                            if 'ExecStart=' in line or 'ExecStartPre=' in line or 'ExecReload=' in line:
                                # Extract path
                                parts = line.split('=', 1)
                                if len(parts) == 2:
                                    cmd_parts = parts[1].strip().split()
                                    if cmd_parts and cmd_parts[0].startswith('/'):
                                        references.add(cmd_parts[0])
                    
                    except Exception:
                        continue
        
        except Exception:
            pass
        
        return references
    
    def _path_to_module(self, file_path: Path) -> str:
        """Convert file path to Python module name."""
        try:
            relative = file_path.relative_to(self.root_path)
            module = str(relative).replace('/', '.').replace('.py', '')
            return module
        except:
            return file_path.stem
    
    def _compute_importance(self, **signals) -> Tuple[float, FileImportance]:
        """
        Compute importance score from multiple signals using configurable weights.

        Returns (importance_score, importance_class)
        where importance_score is 0.0 (low) to 1.0 (critical)
        """
        score = 0.0

        # Git signals (configurable weight, default 40%)
        # Distribute git weight: 75% for tracked, 25% for commit history
        if signals['git_tracked']:
            score += self.git_weight * 0.75  # Tracked files are important
            if signals['git_commits'] > 5:
                score += self.git_weight * 0.25  # Active development history

        # Dependency signals (configurable weight, default 30%)
        # Full dependency weight based on import count
        if signals['imported_by_count'] > 0:
            # Scale: 1 import = 25% of weight, 4+ imports = full weight
            import_score = min(1.0, signals['imported_by_count'] * 0.25)
            score += self.dependency_weight * import_score

        # Systemd signals (configurable weight, default 10%)
        # Full systemd weight if referenced in system services
        if signals['in_systemd']:
            score += self.systemd_weight

        # Usage signals (configurable weight, default 20%)
        # Distribute usage weight: 50% for access time, 50% for modification time
        usage_score = 0.0
        if signals['days_since_access'] < 7:
            usage_score += 0.5  # Recently accessed
        elif signals['days_since_access'] < 30:
            usage_score += 0.25  # Accessed within month

        if signals['days_since_modification'] < 30:
            usage_score += 0.25  # Recently modified
        elif signals['days_since_commit'] < 90 and signals['git_tracked']:
            usage_score += 0.25  # Recent git activity

        score += self.usage_weight * usage_score

        # File type penalties (reduce importance for certain types)
        if signals['is_backup']:
            score -= 0.20  # Backups less important
        if signals['is_cache']:
            score -= 0.30  # Cache files low importance
        if signals['is_temp']:
            score -= 0.25  # Temp files low importance

        # Age penalty (very old files if not git-tracked)
        if not signals['git_tracked'] and signals['age_days'] > 365:
            score -= 0.10

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))

        # Classify using configurable thresholds
        if score >= self.critical_threshold:
            importance_class = FileImportance.CRITICAL
        elif score >= self.important_threshold:
            importance_class = FileImportance.IMPORTANT
        elif score >= self.normal_threshold:
            importance_class = FileImportance.NORMAL
        elif score >= self.low_threshold:
            importance_class = FileImportance.LOW
        else:
            importance_class = FileImportance.OBSOLETE

        return score, importance_class
    
    def _compute_deletion_confidence(self, importance_score: float) -> float:
        """Compute confidence that file can be safely deleted."""
        # Inverse of importance, with exponential scaling
        # High importance (0.8-1.0) -> very low deletion confidence
        # Low importance (0.0-0.2) -> high deletion confidence
        deletion_confidence = (1.0 - importance_score) ** 2
        return deletion_confidence
    
    def should_delete(self, metrics: FileMetrics) -> bool:
        """Determine if file should be deleted based on metrics."""
        # Never delete critical or important files
        if metrics.importance_class in [FileImportance.CRITICAL, FileImportance.IMPORTANT]:
            return False
        
        # Only delete if deletion confidence exceeds threshold
        return metrics.deletion_confidence >= self.min_deletion_confidence
    
    def delete_file(self, metrics: FileMetrics, reason: str) -> bool:
        """
        Delete a file with audit trail and optional archival.
        
        Returns True if deletion successful (or simulated in dry-run).
        """
        file_path = Path(metrics.path)
        
        if not file_path.exists():
            return False
        
        try:
            # Create deletion record
            file_hash = self._compute_file_hash(file_path)
            
            recovery_path = None
            if self.archive_before_delete and not self.dry_run:
                # Archive file before deletion
                recovery_path = self._archive_file(file_path)
            
            deletion_record = DeletionRecord(
                file_path=str(file_path),
                deletion_time=time.time(),
                file_size=metrics.size_bytes,
                file_hash=file_hash,
                importance_score=metrics.importance_score,
                deletion_reason=reason,
                recovery_path=recovery_path,
                metrics=asdict(metrics)
            )
            
            # Log deletion
            self._log_deletion(deletion_record)
            
            if self.dry_run:
                print(f"[DRY-RUN] Would delete: {file_path} (confidence: {metrics.deletion_confidence:.2f})")
                return True
            else:
                # Actually delete
                file_path.unlink()
                print(f"[DELETED] {file_path} (confidence: {metrics.deletion_confidence:.2f})")
                return True
        
        except Exception as e:
            print(f"[ERROR] Failed to delete {file_path}: {e}")
            return False
    
    def _archive_file(self, file_path: Path) -> str:
        """Archive file before deletion for potential recovery."""
        try:
            # Preserve directory structure in archive
            relative_path = file_path.relative_to(self.root_path)
            archive_file = self.archive_path / relative_path
            
            # Create parent directories
            archive_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file to archive
            shutil.copy2(file_path, archive_file)
            
            return str(archive_file)
        
        except Exception as e:
            print(f"[WARNING] Failed to archive {file_path}: {e}")
            return None
    
    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file for verification."""
        try:
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except:
            return ""
    
    def _log_deletion(self, record: DeletionRecord):
        """Append deletion record to audit log."""
        try:
            # Convert record to dict and handle enum serialization
            record_dict = asdict(record)

            # Convert FileImportance enum to string in metrics
            if 'metrics' in record_dict and 'importance_class' in record_dict['metrics']:
                importance = record_dict['metrics']['importance_class']
                if isinstance(importance, FileImportance):
                    record_dict['metrics']['importance_class'] = importance.value

            with open(self.audit_log_path, 'a') as f:
                f.write(json.dumps(record_dict) + '\n')
        except Exception as e:
            print(f"[WARNING] Failed to log deletion: {e}")
    
    def scan_and_cleanup(self, target_dirs: List[str], file_patterns: List[str]) -> Dict[str, Any]:
        """
        Scan directories and perform intelligent cleanup.
        
        Returns statistics about cleanup operation.
        """
        stats = {
            "files_scanned": 0,
            "files_analyzed": 0,
            "files_deleted": 0,
            "files_archived": 0,
            "bytes_freed": 0,
            "importance_distribution": {
                "critical": 0,
                "important": 0,
                "normal": 0,
                "low": 0,
                "obsolete": 0
            },
            "errors": []
        }
        
        print(f"[intelligent_cleanup] Starting scan (dry_run={self.dry_run})")
        print(f"[intelligent_cleanup] Min deletion confidence: {self.min_deletion_confidence}")
        
        for target_dir in target_dirs:
            target_path = Path(target_dir)
            if not target_path.exists():
                continue
            
            for pattern in file_patterns:
                for file_path in target_path.rglob(pattern):
                    stats["files_scanned"] += 1

                    if not file_path.is_file():
                        continue

                    # Skip files in the archive directory to prevent recursive archiving
                    try:
                        if self.archive_path in file_path.parents or file_path == self.archive_path:
                            continue
                    except (ValueError, AttributeError):
                        pass

                    try:
                        # Analyze file
                        metrics = self.analyze_file(file_path)
                        stats["files_analyzed"] += 1
                        stats["importance_distribution"][metrics.importance_class.value] += 1
                        
                        # Decide if should delete
                        if self.should_delete(metrics):
                            if self.delete_file(metrics, f"Automated cleanup (confidence: {metrics.deletion_confidence:.2f})"):
                                stats["files_deleted"] += 1
                                stats["bytes_freed"] += metrics.size_bytes
                                if metrics.importance_score < 0.3:  # Likely archived
                                    stats["files_archived"] += 1
                    
                    except Exception as e:
                        stats["errors"].append(f"{file_path}: {str(e)}")
        
        print(f"[intelligent_cleanup] Scan complete:")
        print(f"  - Scanned: {stats['files_scanned']}")
        print(f"  - Analyzed: {stats['files_analyzed']}")
        print(f"  - Deleted: {stats['files_deleted']}")
        print(f"  - Bytes freed: {stats['bytes_freed']:,}")
        print(f"  - Importance distribution: {stats['importance_distribution']}")
        
        return stats


def test_intelligent_cleanup():
    """Test intelligent cleanup system."""
    cleanup = IntelligentCleanup()
    
    # Test on backup files (safe to test)
    stats = cleanup.scan_and_cleanup(
        target_dirs=["/home/kloros"],
        file_patterns=["*.backup", "*.bak", "*~"]
    )
    
    print("\nTest Results:")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    test_intelligent_cleanup()
