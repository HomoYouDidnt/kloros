#!/usr/bin/env python3
"""KLoROS Obsolete File Sweeper

Finds and marks stale files based on multiple signals:
- Git history (no commits for N days)
- Import/usage graph (nothing imports it)
- System references (not in service files, Dockerfile, etc.)
- Filesystem timestamps (mtime fallback)
- Reachability (not referenced by entrypoints)

Marking policy:
- Python: Insert OBSOLETE banner in module docstring
- Shell/config: Add OBSOLETE comment header
- JSON/binary: Create <file>.obsolete sidecar with metadata

Safety rails:
- Dry-run by default (--apply to mark)
- Allowlist/denylist support
- Track git-tracked files only (unless --include-untracked)
- Grace period before deletion (housekeeping enforces)
- Provenance tracking in marks
"""

import argparse
import os
import re
import subprocess
import sys
import time
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

NOW = time.time()

# Mark provenance metadata
MARK_META = {"source": "sweep_obsolete.py", "version": "1.1"}

# Comment styles by extension
COMMENT_PREFIX = {
    ".py": None,  # docstring edit
    ".sh": "# ",
    ".service": "# ",
    ".timer": "# ",
    ".yaml": "# ",
    ".yml": "# ",
    ".toml": "# ",
    ".cfg": "# ",
    ".ini": "; ",
    ".md": "<!-- ",
}

# GREP command fallback (prefer ripgrep)
try:
    subprocess.check_output(["rg", "--version"], stderr=subprocess.DEVNULL)
    GREP_CMD = ["rg", "-n", "-U"]  # -U: multiline for safety
except Exception:
    GREP_CMD = ["grep", "-R", "-nE"]

# Setup logging
logger = logging.getLogger("kloros.housekeeping.sweep_obsolete")


def load_yaml(p: Path) -> Dict[str, Any]:
    """Load YAML config file."""
    try:
        import yaml
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        logger.error("PyYAML not installed: pip install pyyaml")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load config {p}: {e}")
        sys.exit(1)


def git_last_commit_epoch(path: Path) -> Optional[float]:
    """Get epoch timestamp of last commit touching this file."""
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%ct", "--", str(path)],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return float(out) if out else None
    except Exception:
        return None


def git_tracked(path: Path) -> bool:
    """Check if file is tracked by git."""
    try:
        subprocess.check_output(
            ["git", "ls-files", "--error-unmatch", str(path)],
            stderr=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError:
        return False


def in_allowlist(path: Path, cfg: Dict[str, Any]) -> bool:
    """Check if path matches allowlist patterns."""
    from fnmatch import fnmatch
    for pat in cfg.get("allowlist", []):
        if fnmatch(str(path).replace("\\", "/"), pat):
            return True
    return False


def in_denylist(path: Path, cfg: Dict[str, Any]) -> bool:
    """Check if path matches denylist patterns."""
    from fnmatch import fnmatch
    for pat in cfg.get("denylist_globs", []):
        if fnmatch(str(path).replace("\\", "/"), pat):
            return True
    return False


def python_is_reachable(path: Path, repo_root: Path) -> bool:
    """
    Check if Python module is imported anywhere using heuristic search.
    Handles both absolute and relative imports.
    """
    if path.suffix != ".py":
        return False

    rel = path.relative_to(repo_root).with_suffix("")
    mod_full = ".".join(rel.parts)
    mod_leaf = rel.parts[-1]

    # Search patterns for various import styles
    patterns = [
        rf"(^|\s)from\s+{re.escape(mod_full)}\s+import",
        rf"(^|\s)import\s+{re.escape(mod_full)}(\s|$|,)",
        rf"(^|\s)from\s+[\w\.]+\s+import\s+.*\b{re.escape(mod_leaf)}\b",
        rf"(^|\s)import\s+.*\b{re.escape(mod_leaf)}\b",
    ]

    try:
        for pat in patterns:
            result = subprocess.run(
                GREP_CMD + [pat, str(repo_root)],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0 and result.stdout:
                hits = [l for l in result.stdout.splitlines() if l]
                # Filter out self-references
                hits = [h for h in hits if str(path) not in h]
                if hits:
                    return True
        return False
    except Exception as e:
        logger.debug(f"Import check failed for {path}: {e}")
        return False


def referenced_in_system_files(path: Path, repo_root: Path) -> bool:
    """Check if filename appears in system config files."""
    name = path.name
    candidates = []

    # Scan system configuration files
    for glob in ["**/Dockerfile", "services/**/*.service", "services/**/*.timer",
                 "**/*.sh", "pyproject.toml", "setup.cfg", "Makefile",
                 "**/*.yaml", "**/*.yml"]:
        candidates.extend(repo_root.glob(glob))

    for c in candidates:
        try:
            if c.is_file() and name in c.read_text(errors="ignore"):
                return True
        except Exception:
            pass
    return False


def file_old_enough(path: Path, threshold_days: int) -> bool:
    """Check if file mtime is older than threshold."""
    try:
        st = path.stat()
        mtime = st.st_mtime
        return (NOW - mtime) > threshold_days * 86400
    except Exception:
        return False


def git_old_enough(path: Path, threshold_days: int) -> bool:
    """Check if file hasn't been committed to in N days."""
    last = git_last_commit_epoch(path)
    if last is None:
        # Untracked or no git—fallback to mtime
        return file_old_enough(path, threshold_days)
    return (NOW - last) > threshold_days * 86400


def write_sidecar_mark(p: Path, reason: str) -> Path:
    """Write obsolete mark to sidecar file for no-comment formats."""
    meta = {
        "type": "OBSOLETE",
        "reason": reason,
        "ts": int(NOW),
        **MARK_META
    }
    sc = p.with_suffix(p.suffix + ".obsolete")
    sc.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return sc


OBSOLETE_RX = re.compile(r"^\s*(?:[ruRU]?[fF]?)?[\"']{3}\s*OBSOLETE:", re.M)


def mark_python_docstring(p: Path, reason: str) -> bool:
    """Insert OBSOLETE banner into Python module docstring."""
    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")

        # Already marked?
        if OBSOLETE_RX.search(txt):
            return False

        # Check for existing docstring
        m = re.match(r"^\s*[\"']{3}(.|\n)*?[\"']{3}", txt)
        banner = f'"""OBSOLETE: {reason} ({MARK_META["source"]}:{MARK_META["version"]})"""\n'

        if m and m.start() == 0:
            # Prepend to existing docstring
            first = m.group(0)
            new = banner + txt[len(first):]
        else:
            # Add as first line
            new = banner + txt

        p.write_text(new, encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"Failed to mark Python docstring {p}: {e}")
        return False


def mark_text_header(p: Path, reason: str) -> bool:
    """Add OBSOLETE marker to file header (or sidecar for unsupported formats)."""
    ext = p.suffix.lower()

    if ext not in COMMENT_PREFIX:
        # No comment style → use sidecar
        write_sidecar_mark(p, reason)
        return True

    prefix = COMMENT_PREFIX[ext]
    if prefix is None:
        # Python → use docstring
        return mark_python_docstring(p, reason)

    try:
        txt = p.read_text(encoding="utf-8", errors="ignore")

        # Already marked?
        if txt.startswith(prefix + "OBSOLETE:"):
            return False

        # Format header by file type
        if ext == ".md":
            header = f"<!-- OBSOLETE: {reason} ({MARK_META['source']}:{MARK_META['version']}) -->\n"
        elif prefix.strip() == ";":
            header = f"; OBSOLETE: {reason} ({MARK_META['source']}:{MARK_META['version']})\n"
        else:
            header = f"{prefix}OBSOLETE: {reason} ({MARK_META['source']}:{MARK_META['version']})\n"

        p.write_text(header + txt, encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"Failed to mark text header {p}: {e}")
        return False


def has_been_marked_long_enough(path: Path, grace_days: int) -> bool:
    """Check if OBSOLETE mark is old enough to permit deletion."""
    # Check sidecar first (fast)
    sc = path.with_suffix(path.suffix + ".obsolete")
    if sc.exists():
        try:
            meta = json.loads(sc.read_text(encoding="utf-8"))
            mark_age_days = (NOW - float(meta.get("ts", NOW))) / 86400
            return mark_age_days >= grace_days
        except Exception:
            pass

    # Fallback: git blame on first 10 lines for OBSOLETE
    try:
        out = subprocess.check_output(
            ["git", "blame", "-L", "1,10", "--", str(path)],
            stderr=subprocess.DEVNULL
        ).decode()

        for line in out.splitlines():
            if "OBSOLETE" in line:
                # Extract commit hash
                commit = line.split()[0].strip("^")
                # Get commit timestamp
                ts = subprocess.check_output(
                    ["git", "show", "-s", "--format=%ct", commit],
                    stderr=subprocess.DEVNULL
                ).decode().strip()
                mark_age_days = (NOW - float(ts)) / 86400
                return mark_age_days >= grace_days
    except Exception:
        pass

    return False


def scan_for_candidates(
    repo_root: Path,
    cfg: Dict[str, Any],
    include_untracked: bool
) -> List[Dict[str, Any]]:
    """Scan repository for obsolete file candidates."""
    threshold = int(cfg.get("threshold_days", 90))
    score_threshold = int(cfg.get("score_threshold", 3))

    roots = [repo_root / r for r in cfg.get("roots", ["."])]
    exts = set(cfg.get("languages", {}).get("python", {}).get("exts", [".py"]))
    exts |= set(cfg.get("other_text_exts", []))

    candidates = []

    for rt in roots:
        for p in rt.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in exts:
                continue

            rel = p.relative_to(repo_root)

            # Apply filters
            if in_allowlist(rel, cfg):
                continue
            if in_denylist(rel, cfg):
                continue
            if not include_untracked and not git_tracked(p):
                continue

            # Check for KEEP: opt-out marker
            try:
                first_line = p.read_text(encoding="utf-8", errors="ignore").split("\n")[0]
                if "KEEP:" in first_line.upper():
                    continue
            except Exception:
                pass

            # Compute staleness signals
            old_git = git_old_enough(p, threshold)
            old_fs = file_old_enough(p, threshold)
            reach = python_is_reachable(p, repo_root) if p.suffix == ".py" else False
            refsys = referenced_in_system_files(p, repo_root)

            # Score: each negative signal adds 1 point
            score = 0
            score += 1 if old_git else 0
            score += 1 if old_fs else 0
            score += 0 if reach else 1  # Not reachable = +1
            score += 0 if refsys else 1  # Not referenced = +1

            # High confidence obsolete if score >= threshold
            if score >= score_threshold:
                candidates.append({
                    "path": str(rel),
                    "score": score,
                    "signals": {
                        "git_old": old_git,
                        "mtime_old": old_fs,
                        "python_reachable": reach,
                        "referenced_in_system": refsys
                    }
                })

    return candidates


def main():
    """Main entry point."""
    ap = argparse.ArgumentParser(
        description="Find & mark obsolete files for KLoROS housekeeping."
    )
    ap.add_argument("--config", default="/home/kloros/.kloros/obsolete_sweeper.yaml",
                    help="Path to config YAML")
    ap.add_argument("--apply", action="store_true",
                    help="Write OBSOLETE markers into files")
    ap.add_argument("--root", default="/home/kloros",
                    help="Repository root directory")
    ap.add_argument("--include-untracked", action="store_true",
                    help="Include untracked files in scan")
    args = ap.parse_args()

    repo_root = Path(args.root).resolve()
    cfg = load_yaml(Path(args.config))

    # Scan for candidates
    candidates = scan_for_candidates(
        repo_root,
        cfg,
        args.include_untracked
    )

    # Build report
    report = {
        "threshold_days": cfg.get("threshold_days", 90),
        "grace_days_after_mark": cfg.get("grace_days_after_mark", 14),
        "score_threshold": cfg.get("score_threshold", 3),
        "count": len(candidates),
        "items": candidates
    }

    # Print report to stdout
    print(json.dumps(report, indent=2))

    # Persist report
    report_path = Path("/home/kloros/.kloros/logs/obsolete_sweep_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Log to KLoROS logger
    try:
        logger.info(f"obsolete_sweep completed: {len(candidates)} candidates found")
        logger.info(f"report saved to {report_path}")
    except Exception:
        pass

    # Apply marks if requested
    if args.apply:
        marked_count = 0
        threshold_days = cfg.get("threshold_days", 90)
        reason = f"Stale {threshold_days}d; no refs/imports; auto-marked by housekeeping."

        for item in candidates:
            p = repo_root / item["path"]
            try:
                if mark_text_header(p, reason):
                    marked_count += 1
                    logger.info(f"Marked: {item['path']}")
            except Exception as e:
                logger.error(f"Failed to mark {item['path']}: {e}")

        print(f"\nMarked {marked_count}/{len(candidates)} files", file=sys.stderr)


if __name__ == "__main__":
    main()
