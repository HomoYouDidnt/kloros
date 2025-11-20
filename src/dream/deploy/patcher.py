#!/usr/bin/env python3
"""
D-REAM AST-safe Deployment Patcher
Safe code modification using libcst for production deployments.
"""

import ast
import difflib
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple
import logging

# Try libcst first, fall back to ast if not available
try:
    import libcst as cst
    LIBCST_AVAILABLE = True
except ImportError:
    LIBCST_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("libcst not available, using ast fallback (less precise)")

logger = logging.getLogger(__name__)


@dataclass
class ChangeRequest:
    """Request for AST-safe code modification."""
    file_path: str
    target_class: Optional[str]
    target_func: str
    new_impl_src: str
    precondition: Optional[str] = None
    postcondition: Optional[str] = None
    metadata: dict = None

    def validate(self) -> bool:
        """Validate the change request."""
        # Check file exists
        if not Path(self.file_path).exists():
            raise FileNotFoundError(f"Target file not found: {self.file_path}")

        # Basic validation of new implementation
        try:
            ast.parse(self.new_impl_src)
        except SyntaxError as e:
            raise ValueError(f"Invalid Python syntax in new implementation: {e}")

        return True


if LIBCST_AVAILABLE:
    class FuncRewriter(cst.CSTTransformer):
        """CST transformer for function replacement."""

        def __init__(self, cr: ChangeRequest):
            self.cr = cr
            self.applied = False
            self.in_target_class = False

        def visit_ClassDef(self, node: cst.ClassDef) -> None:
            """Track when we enter target class."""
            if self.cr.target_class and node.name.value == self.cr.target_class:
                self.in_target_class = True

        def leave_ClassDef(self, original: cst.ClassDef, updated: cst.ClassDef) -> cst.ClassDef:
            """Track when we leave target class."""
            if self.cr.target_class and original.name.value == self.cr.target_class:
                self.in_target_class = False
            return updated

        def leave_FunctionDef(self, original: cst.FunctionDef, 
                            updated: cst.FunctionDef) -> cst.FunctionDef:
            """Replace target function."""
            name = original.name.value
            
            # Check if this is our target
            is_target = (name == self.cr.target_func and 
                        (not self.cr.target_class or self.in_target_class))

            if is_target:
                try:
                    # Parse new implementation
                    new_module = cst.parse_module(self.cr.new_impl_src)
                    
                    # Extract first function/statement
                    if new_module.body and isinstance(new_module.body[0], cst.FunctionDef):
                        new_func = new_module.body[0]
                        self.applied = True
                        logger.info(f"Replacing function {name} with new implementation")
                        return new_func
                    else:
                        # Try to parse as just the body
                        new_body = cst.parse_statement(f"def {name}():\n" + 
                                                      self.cr.new_impl_src).body
                        self.applied = True
                        return updated.with_changes(body=new_body)
                except Exception as e:
                    logger.error(f"Failed to parse new implementation: {e}")
                    raise

            return updated


class ASTFallbackPatcher:
    """Fallback patcher using standard ast module."""

    @staticmethod
    def apply_change(cr: ChangeRequest) -> str:
        """Apply change using ast (less precise than libcst)."""
        with open(cr.file_path, 'r', encoding='utf-8') as f:
            source = f.read()

        tree = ast.parse(source)
        
        # Find and replace target function
        class FuncReplacer(ast.NodeTransformer):
            def __init__(self):
                self.applied = False
                self.in_class = None

            def visit_ClassDef(self, node):
                old_in_class = self.in_class
                if cr.target_class and node.name == cr.target_class:
                    self.in_class = node.name
                self.generic_visit(node)
                self.in_class = old_in_class
                return node

            def visit_FunctionDef(self, node):
                is_target = (node.name == cr.target_func and
                           (not cr.target_class or self.in_class == cr.target_class))
                
                if is_target:
                    # Parse new implementation
                    new_tree = ast.parse(cr.new_impl_src)
                    if new_tree.body and isinstance(new_tree.body[0], ast.FunctionDef):
                        self.applied = True
                        return new_tree.body[0]
                return node

        replacer = FuncReplacer()
        new_tree = replacer.visit(tree)
        
        if not replacer.applied:
            raise ValueError(f"Target function {cr.target_func} not found")

        # Convert back to source
        import astor
        return astor.to_source(new_tree)


def apply_change(cr: ChangeRequest) -> str:
    """
    Apply a change request to generate patched code.

    Args:
        cr: Change request specification

    Returns:
        Patched source code
    """
    cr.validate()

    if LIBCST_AVAILABLE:
        with open(cr.file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        mod = cst.parse_module(source)
        transformer = FuncRewriter(cr)
        new_mod = mod.visit(transformer)
        
        if not transformer.applied:
            raise ValueError(f"Target function {cr.target_func} not found in {cr.file_path}")
        
        return new_mod.code
    else:
        return ASTFallbackPatcher.apply_change(cr)


def create_patch(original: str, modified: str, 
                file_path: str = "file") -> str:
    """
    Create unified diff patch.

    Args:
        original: Original source code
        modified: Modified source code
        file_path: File path for diff header

    Returns:
        Unified diff patch string
    """
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm=""
    )
    
    return "".join(diff)


def apply_patch_to_file(patch_content: str, target_file: str) -> bool:
    """
    Apply a patch to a file using patch utility.

    Args:
        patch_content: Patch content
        target_file: Target file to patch

    Returns:
        True if successful
    """
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
        f.write(patch_content)
        patch_file = f.name

    try:
        result = subprocess.run(
            ['patch', '-p1', target_file],
            input=patch_content,
            text=True,
            capture_output=True
        )
        return result.returncode == 0
    finally:
        Path(patch_file).unlink(missing_ok=True)


@dataclass
class PatchArtifact:
    """Patch artifact with metadata."""
    patch_id: str
    file_path: str
    original_hash: str
    patched_hash: str
    patch_content: str
    change_request: ChangeRequest
    timestamp: str

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'patch_id': self.patch_id,
            'file_path': self.file_path,
            'original_hash': self.original_hash,
            'patched_hash': self.patched_hash,
            'patch_size': len(self.patch_content),
            'target_func': self.change_request.target_func,
            'target_class': self.change_request.target_class,
            'timestamp': self.timestamp
        }


class PatchManager:
    """Manage patch application and rollback."""

    def __init__(self, artifacts_dir: str = "artifacts"):
        self.artifacts_dir = Path(artifacts_dir)
        self.patches_dir = self.artifacts_dir / "patches"
        self.backups_dir = self.artifacts_dir / "backups"
        
        # Create directories
        self.patches_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def apply(self, cr: ChangeRequest, dry_run: bool = True) -> PatchArtifact:
        """
        Apply a change request with backup.

        Args:
            cr: Change request
            dry_run: If True, generate patch but don't apply

        Returns:
            PatchArtifact with details
        """
        from datetime import datetime
        
        # Read original file
        file_path = Path(cr.file_path)
        original_content = file_path.read_text(encoding='utf-8')
        original_hash = hashlib.sha256(original_content.encode()).hexdigest()

        # Generate patched version
        patched_content = apply_change(cr)
        patched_hash = hashlib.sha256(patched_content.encode()).hexdigest()

        # Create patch
        patch_content = create_patch(original_content, patched_content, str(file_path))

        # Generate patch ID
        timestamp = datetime.now().isoformat()
        patch_id = f"{file_path.stem}_{cr.target_func}_{timestamp.replace(':', '-')}"

        # Create artifact
        artifact = PatchArtifact(
            patch_id=patch_id,
            file_path=str(file_path),
            original_hash=original_hash,
            patched_hash=patched_hash,
            patch_content=patch_content,
            change_request=cr,
            timestamp=timestamp
        )

        if not dry_run:
            # Backup original
            backup_path = self.backups_dir / f"{patch_id}.bak"
            shutil.copy2(file_path, backup_path)
            logger.info(f"Backed up original to {backup_path}")

            # Apply patch
            file_path.write_text(patched_content, encoding='utf-8')
            logger.info(f"Applied patch to {file_path}")

            # Save patch file
            patch_path = self.patches_dir / f"{patch_id}.patch"
            patch_path.write_text(patch_content, encoding='utf-8')
            logger.info(f"Saved patch to {patch_path}")

        return artifact

    def rollback(self, patch_id: str) -> bool:
        """
        Rollback a patch using backup.

        Args:
            patch_id: Patch ID to rollback

        Returns:
            True if successful
        """
        backup_path = self.backups_dir / f"{patch_id}.bak"
        
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_path}")
            return False

        # Find original file from patch metadata
        # (In production, load from manifest)
        patch_files = list(self.patches_dir.glob(f"{patch_id}*"))
        if not patch_files:
            logger.error(f"Patch file not found for {patch_id}")
            return False

        # For now, derive from patch_id
        parts = patch_id.split('_')
        if len(parts) < 2:
            logger.error(f"Invalid patch_id format: {patch_id}")
            return False

        file_name = parts[0]
        # Search for file
        candidates = list(Path.cwd().rglob(f"{file_name}.py"))
        if not candidates:
            logger.error(f"Target file not found: {file_name}.py")
            return False

        target_file = candidates[0]
        
        # Restore backup
        shutil.copy2(backup_path, target_file)
        logger.info(f"Rolled back {target_file} from {backup_path}")
        
        return True


def validate_patch(cr: ChangeRequest, test_command: Optional[str] = None) -> bool:
    """
    Validate a patch before deployment.

    Args:
        cr: Change request
        test_command: Optional test command to run

    Returns:
        True if validation passes
    """
    try:
        # Generate patched code (syntax check)
        patched = apply_change(cr)
        
        # Parse to verify syntax
        ast.parse(patched)
        
        # Run test command if provided
        if test_command:
            import subprocess
            result = subprocess.run(test_command, shell=True, capture_output=True)
            if result.returncode != 0:
                logger.error(f"Test failed: {result.stderr.decode()}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return False
