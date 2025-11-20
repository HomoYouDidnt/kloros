"""
D-REAM spawn utility: create new SPICA instances from template.

This module provides deterministic, auditable instance creation:
- Clones template with .templateignore exclusions
- Writes immutable lineage.json (spica_id, parent_id, origin_commit, generation)
- Generates manifest.json with tamper-evidence (lineage_sha)
- Applies mutations (hyperparameters, prompts, etc.)
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

# Paths
SPICA_ROOT = Path("/home/kloros/experiments/spica")
TEMPLATE = SPICA_ROOT / "template"
INSTANCES = SPICA_ROOT / "instances"
TEMPLATEIGNORE = TEMPLATE / ".templateignore"


def _git_sha(repo: Path = SPICA_ROOT) -> str:
    """Get current git commit SHA (8-char short)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "unknown"


def _rsync_template(src: Path, dst: Path) -> None:
    """Clone template using rsync with .templateignore exclusions."""
    dst.mkdir(parents=True, exist_ok=True)

    # Build rsync exclude args from .templateignore
    excludes = []
    if TEMPLATEIGNORE.exists():
        for line in TEMPLATEIGNORE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                excludes.extend(["--exclude", line])

    # rsync -a (archive mode) with exclusions
    # Note: .venv/ is excluded, so no need for --copy-links
    cmd = ["rsync", "-a"] + excludes + [f"{src}/", f"{dst}/"]

    # Retry logic for transient errors (exit code 23 = partial transfer)
    max_retries = 2
    for attempt in range(max_retries):
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            return  # Success
        except subprocess.CalledProcessError as e:
            if e.returncode == 23 and attempt < max_retries - 1:
                # Partial transfer error - retry once
                import time
                time.sleep(0.1)  # Brief delay before retry
                continue
            # Other errors or final retry failed - raise with stderr
            stderr_msg = e.stderr.strip() if e.stderr else "no stderr"
            raise subprocess.CalledProcessError(
                e.returncode, e.cmd, e.output,
                stderr=f"rsync error (code {e.returncode}): {stderr_msg}"
            )


def _hash_file(path: Path) -> str:
    """Compute SHA256 hash of file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spawn_instance(
    mutations: dict | None = None,
    parent_id: str | None = None,
    budget: dict | None = None,
    notes: str = "",
    auto_prune: bool = True
) -> str:
    """
    Spawn a new SPICA instance from template.

    Args:
        mutations: Hyperparameter/config mutations (e.g., {"tau_persona": 0.03})
        parent_id: Parent instance ID (if this is a child/fork)
        budget: Resource limits (e.g., {"cpu": 4, "ram_gb": 8, "vram_gb": 8})
        notes: Human-readable notes about this spawn
        auto_prune: Auto-prune old instances before spawning (default: True)

    Returns:
        spica_id: The new instance identifier

    Raises:
        RuntimeError: If template or spawn fails
    """
    # Auto-prune old instances to prevent unbounded growth
    if auto_prune:
        max_instances = int(os.environ.get("SPICA_RETENTION_MAX_INSTANCES", "5"))
        max_age_days = int(os.environ.get("SPICA_RETENTION_MAX_AGE_DAYS", "3"))
        try:
            prune_instances(max_instances=max_instances, max_age_days=max_age_days, dry_run=False)
        except Exception as e:
            # Log warning but don't fail spawn
            print(f"Warning: Auto-prune failed: {e}", file=sys.stderr)

    # Validate template exists
    if not TEMPLATE.exists():
        raise RuntimeError(f"Template not found: {TEMPLATE}")

    if not (TEMPLATE / "VERSION").exists():
        raise RuntimeError(f"Template VERSION file missing: {TEMPLATE}/VERSION")

    # Generate unique instance ID
    spica_id = f"spica-{uuid.uuid4().hex[:8]}"
    dst = INSTANCES / spica_id

    try:
        # Clone template
        try:
            _rsync_template(TEMPLATE, dst)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"rsync failed: {e}")

        # Read template version
        template_version = (TEMPLATE / "VERSION").read_text().strip()

        # Write lineage.json FIRST (needed for tamper-evidence hash)
        lineage = {
            "spica_id": spica_id,
            "parent_id": parent_id,
            "origin_commit": _git_sha(),
            "generation": 0,
            "spawned_at": datetime.now(timezone.utc).isoformat()
        }
        lineage_path = dst / "lineage.json"
        lineage_path.write_text(json.dumps(lineage, indent=2) + "\n")

        # Compute lineage hash for tamper-evidence
        lineage_sha = _hash_file(lineage_path)

        # Deterministic seed (based on spawn time, for reproducibility)
        seed = int(time.time()) & 0xffffffff

        # Build manifest with tamper-evidence
        manifest = {
            "schema": "spica.manifest/v1",
            "spica_id": spica_id,
            "template_ref": f"git:{_git_sha()}",
            "template_version": template_version,
            "lineage_sha": lineage_sha,  # TAMPER EVIDENCE
            "seed": seed,
            "params": mutations or {},
            "budget": budget or {
                "cpu": int(os.environ.get("SPICA_BUDGET_CPU", "4")),
                "ram_gb": int(os.environ.get("SPICA_BUDGET_RAM_GB", "8")),
                "vram_gb": int(os.environ.get("SPICA_BUDGET_VRAM_GB", "8"))
            },
            "spawned_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes
        }

        manifest_path = dst / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Apply mutations to instance .env.spica (if provided)
        if mutations:
            env_path = dst / ".env.spica"
            if env_path.exists():
                env_content = env_path.read_text()
                # Simple key=value mutation (can be extended)
                for key, value in mutations.items():
                    if isinstance(value, (int, float)):
                        env_content += f"\n{key}={value}\n"
                env_path.write_text(env_content)

        # Verify instance completeness before returning
        if not lineage_path.exists() or not manifest_path.exists():
            raise RuntimeError(f"Instance creation incomplete: missing required files")

        # Create preliminary tournament lock if spawned for tournament (auto_prune=False)
        # This protects instance from concurrent pruning before submit_tournament() runs
        if not auto_prune:
            lock_file = dst / ".tournament_lock"
            lock_data = {
                "tournament_id": f"prelim_{int(time.time())}_{spica_id}",
                "suite_id": "pending",
                "started_at": time.time(),
                "instances": [spica_id],
                "note": "Preliminary lock created during spawn (auto_prune=False)"
            }
            lock_file.write_text(json.dumps(lock_data, indent=2))

        return spica_id

    except Exception as e:
        # Clean up incomplete instance on ANY failure
        if dst.exists():
            import shutil
            try:
                shutil.rmtree(dst)
                print(f"Cleaned up incomplete instance {spica_id}: {e}", file=sys.stderr)
            except Exception as cleanup_error:
                print(f"Failed to clean up {spica_id}: {cleanup_error}", file=sys.stderr)
        raise RuntimeError(f"Failed to spawn instance {spica_id}: {e}")


def verify_lineage_integrity(instance_id: str) -> bool:
    """
    Verify lineage.json hasn't been tampered with.

    Args:
        instance_id: The SPICA instance ID

    Returns:
        True if lineage hash matches manifest, False otherwise
    """
    instance_path = INSTANCES / instance_id
    lineage_path = instance_path / "lineage.json"
    manifest_path = instance_path / "manifest.json"

    if not lineage_path.exists() or not manifest_path.exists():
        return False

    # Compute current lineage hash
    current_hash = _hash_file(lineage_path)

    # Load expected hash from manifest
    manifest = json.loads(manifest_path.read_text())
    expected_hash = manifest.get("lineage_sha")

    return current_hash == expected_hash


def list_instances() -> list[dict]:
    """List all spawned SPICA instances with metadata."""
    if not INSTANCES.exists():
        return []

    instances = []
    for instance_dir in INSTANCES.iterdir():
        if not instance_dir.is_dir():
            continue

        manifest_path = instance_dir / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text())
            instances.append({
                "spica_id": manifest.get("spica_id"),
                "template_version": manifest.get("template_version"),
                "spawned_at": manifest.get("spawned_at"),
                "integrity_ok": verify_lineage_integrity(instance_dir.name)
            })
        except (json.JSONDecodeError, KeyError):
            continue

    return sorted(instances, key=lambda x: x.get("spawned_at", ""), reverse=True)


def prune_instances(max_instances: int = 5, max_age_days: int = 7, dry_run: bool = False) -> dict:
    """
    Prune old SPICA instances to prevent unbounded disk growth.

    Retention policy:
    - Keep at most max_instances (newest by spawn time)
    - Delete instances older than max_age_days
    - Always preserve instances with active tournament references

    Args:
        max_instances: Maximum number of instances to keep (default: 5, aligned with ResourceGovernor)
        max_age_days: Maximum age in days before deletion (default: 7)
        dry_run: If True, report what would be deleted without removing

    Returns:
        dict with pruned/kept counts and disk space reclaimed

    Raises:
        RuntimeError: If INSTANCES path is unsafe or operation exceeds budget
    """
    if not INSTANCES.exists():
        return {"pruned": 0, "kept": 0, "space_reclaimed_gb": 0.0}

    # Safety: Ensure we're only operating in the sandboxed SPICA instances path
    if not str(INSTANCES.resolve()).startswith("/home/kloros/experiments/spica/instances"):
        raise RuntimeError(f"Unsafe prune path: {INSTANCES}")

    # First pass: Clean up incomplete instances (missing manifest/lineage)
    incomplete_cleaned = 0
    incomplete_space_reclaimed = 0
    for instance_dir in INSTANCES.iterdir():
        if not instance_dir.is_dir():
            continue

        manifest_path = instance_dir / "manifest.json"
        lineage_path = instance_dir / "lineage.json"

        # Incomplete instance: missing either manifest or lineage
        if not manifest_path.exists() or not lineage_path.exists():
            try:
                size_bytes = sum(f.stat().st_size for f in instance_dir.rglob("*") if f.is_file())

                if dry_run:
                    print(f"[DRY-RUN] Would clean incomplete instance: {instance_dir.name} (size={size_bytes/(1024**3):.2f}GB)")
                    incomplete_space_reclaimed += size_bytes
                    incomplete_cleaned += 1
                else:
                    import shutil
                    import stat

                    def handle_remove_readonly(func, path, exc):
                        if isinstance(exc[1], PermissionError):
                            import subprocess
                            try:
                                subprocess.run(
                                    ["sudo", "chown", "-R", "kloros:kloros", str(instance_dir)],
                                    check=True,
                                    capture_output=True
                                )
                                os.chmod(path, stat.S_IWUSR)
                                func(path)
                            except Exception as fix_err:
                                print(f"Warning: Could not fix permissions for {path}: {fix_err}", file=sys.stderr)
                        else:
                            raise

                    shutil.rmtree(instance_dir, onerror=handle_remove_readonly)
                    incomplete_space_reclaimed += size_bytes
                    incomplete_cleaned += 1
                    print(f"Cleaned incomplete instance: {instance_dir.name}", file=sys.stderr)
            except (OSError, Exception) as e:
                print(f"Warning: Failed to clean incomplete instance {instance_dir.name}: {e}", file=sys.stderr)

    # Get all valid instances with metadata
    instances = []
    for instance_dir in INSTANCES.iterdir():
        if not instance_dir.is_dir():
            continue

        manifest_path = instance_dir / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text())
            spawned_at = manifest.get("spawned_at", "")

            # Parse ISO timestamp
            try:
                spawn_time = datetime.fromisoformat(spawned_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                # Invalid timestamp - treat as very old
                spawn_time = datetime.min.replace(tzinfo=timezone.utc)

            age_days = (datetime.now(timezone.utc) - spawn_time).days

            # Get disk usage (bounded operation - max 1000 instances)
            size_bytes = sum(f.stat().st_size for f in instance_dir.rglob("*") if f.is_file())

            # Check for tournament lock file
            lock_file = instance_dir / ".tournament_lock"
            tournament_locked = lock_file.exists()

            # If locked, check if lock is stale (older than 1 hour)
            if tournament_locked:
                try:
                    lock_data = json.loads(lock_file.read_text())
                    lock_age_seconds = time.time() - lock_data.get("started_at", 0)
                    # Locks older than 1 hour are considered stale
                    if lock_age_seconds > 3600:
                        import logging
                        logging.warning(f"Removing stale tournament lock for {manifest.get('spica_id')} (age={lock_age_seconds/60:.1f}min)")
                        lock_file.unlink()
                        tournament_locked = False
                except Exception:
                    # Corrupt lock file - remove it
                    lock_file.unlink()
                    tournament_locked = False

            instances.append({
                "spica_id": manifest.get("spica_id"),
                "path": instance_dir,
                "spawned_at": spawned_at,
                "age_days": age_days,
                "size_bytes": size_bytes,
                "tournament_locked": tournament_locked
            })
        except (json.JSONDecodeError, KeyError, OSError):
            continue

    # Sort by spawn time (newest first)
    instances.sort(key=lambda x: x["spawned_at"], reverse=True)

    # Determine what to keep vs prune
    to_keep = []
    to_prune = []
    tournament_protected = 0

    for i, inst in enumerate(instances):
        # ALWAYS keep tournament-locked instances (active tournaments)
        if inst.get("tournament_locked", False):
            to_keep.append(inst)
            tournament_protected += 1
            continue

        # Keep if within count limit AND age limit
        if i < max_instances and inst["age_days"] < max_age_days:
            to_keep.append(inst)
        else:
            to_prune.append(inst)

    # Execute pruning
    space_reclaimed = 0
    pruned_count = 0

    for inst in to_prune:
        if dry_run:
            print(f"[DRY-RUN] Would prune: {inst['spica_id']} (age={inst['age_days']}d, size={inst['size_bytes']/(1024**3):.2f}GB)")
            space_reclaimed += inst["size_bytes"]
            pruned_count += 1
        else:
            try:
                # Bounded deletion - use shutil.rmtree with safety checks
                import shutil
                if inst["path"].exists() and inst["path"].is_dir():
                    shutil.rmtree(inst["path"])
                    space_reclaimed += inst["size_bytes"]
                    pruned_count += 1
            except OSError as e:
                # Log error but continue
                print(f"Warning: Failed to prune {inst['spica_id']}: {e}", file=sys.stderr)

    result = {
        "pruned": pruned_count,
        "kept": len(to_keep),
        "tournament_protected": tournament_protected,
        "incomplete_cleaned": incomplete_cleaned,
        "space_reclaimed_gb": (space_reclaimed + incomplete_space_reclaimed) / (1024**3)
    }

    # Log to KLoROS structured log (with fallback)
    log_dir = Path("/var/log/kloros")

    # Check if we can write to /var/log/kloros, otherwise use fallback
    try:
        if not log_dir.exists() or not os.access(log_dir, os.W_OK):
            raise PermissionError("Cannot write to /var/log/kloros")
        log_path = log_dir / "spica_retention.jsonl"
    except (PermissionError, OSError):
        # Fallback to user directory
        log_dir = Path.home() / ".kloros" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "spica_retention.jsonl"

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "prune_instances",
        "dry_run": dry_run,
        **result
    }

    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except (OSError, PermissionError) as e:
        # Log to stderr if file write fails
        print(f"Warning: Could not write audit log to {log_path}: {e}", file=sys.stderr)

    return result


if __name__ == "__main__":
    # CLI usage example
    import sys

    if len(sys.argv) < 2:
        print("Usage: python spica_spawn.py <command>")
        print("Commands:")
        print("  spawn [--parent <id>] [--notes <text>]  - Spawn new instance")
        print("  list                                     - List all instances")
        print("  verify <instance_id>                     - Verify lineage integrity")
        print("  prune [--max-instances N] [--max-age-days N] [--dry-run]  - Prune old instances")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "spawn":
        parent = None
        notes = ""
        if "--parent" in sys.argv:
            idx = sys.argv.index("--parent")
            parent = sys.argv[idx + 1]
        if "--notes" in sys.argv:
            idx = sys.argv.index("--notes")
            notes = sys.argv[idx + 1]

        spica_id = spawn_instance(parent_id=parent, notes=notes)
        print(json.dumps({"spica_id": spica_id, "status": "spawned"}, indent=2))

    elif cmd == "list":
        instances = list_instances()
        print(json.dumps(instances, indent=2))

    elif cmd == "verify":
        if len(sys.argv) < 3:
            print("ERROR: verify requires instance_id", file=sys.stderr)
            sys.exit(1)
        instance_id = sys.argv[2]
        ok = verify_lineage_integrity(instance_id)
        print(json.dumps({"instance_id": instance_id, "integrity_ok": ok}, indent=2))
        sys.exit(0 if ok else 1)

    elif cmd == "prune":
        max_instances = 5  # Aligned with ResourceGovernor limit
        max_age_days = 7
        dry_run = False

        if "--max-instances" in sys.argv:
            idx = sys.argv.index("--max-instances")
            max_instances = int(sys.argv[idx + 1])
        if "--max-age-days" in sys.argv:
            idx = sys.argv.index("--max-age-days")
            max_age_days = int(sys.argv[idx + 1])
        if "--dry-run" in sys.argv:
            dry_run = True

        result = prune_instances(max_instances, max_age_days, dry_run)
        print(json.dumps(result, indent=2))

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
