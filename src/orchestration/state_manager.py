#!/usr/bin/env python3
"""
State Manager - Lock management for KLoROS orchestration.

Provides exclusive locks using fcntl with PID tracking and stale detection.
"""

import os
import json
import fcntl
import socket
import time
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

LOCK_DIR = Path("/home/kloros/.kloros/locks")


@dataclass
class LockHandle:
    """Represents an acquired lock."""
    name: str
    pid: int
    hostname: str
    started_at: float
    path: Path
    _fd: Optional[int] = None  # File descriptor (internal)


def acquire(name: str, ttl_s: int = 600) -> LockHandle:
    """
    Acquire exclusive lock with fcntl.

    Args:
        name: Lock name (e.g., "orchestrator", "phase", "dream")
        ttl_s: Time-to-live for stale detection (default 10 minutes)

    Returns:
        LockHandle with file descriptor

    Raises:
        RuntimeError: If lock cannot be acquired or is held by another process
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)

    lock_path = LOCK_DIR / f"{name}.lock"

    # Check for stale locks first
    if lock_path.exists():
        try:
            with open(lock_path, 'r') as f:
                existing = json.load(f)

            existing_pid = existing.get("pid")
            started = existing.get("started_at", 0)

            # Check if process is still alive
            if existing_pid:
                try:
                    os.kill(existing_pid, 0)  # Signal 0 just checks existence
                    # Process exists - check if stale
                    if time.time() - started > ttl_s:
                        logger.warning(f"Lock {name} held by PID {existing_pid} exceeded TTL ({ttl_s}s), reaping")
                    else:
                        raise RuntimeError(f"Lock {name} already held by PID {existing_pid}")
                except ProcessLookupError:
                    # Process doesn't exist - stale lock (normal for oneshot services)
                    logger.debug(f"Reaping stale lock {name} from dead PID {existing_pid}")
        except Exception as e:
            logger.warning(f"Error checking existing lock: {e}")

    # Open lock file with exclusive flag
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    except Exception as e:
        raise RuntimeError(f"Failed to open lock file {lock_path}: {e}")

    # Try to acquire exclusive lock (non-blocking)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise RuntimeError(f"Lock {name} is held by another process (fcntl blocked)")
    except Exception as e:
        os.close(fd)
        raise RuntimeError(f"Failed to acquire lock {name}: {e}")

    # Write lock metadata
    handle = LockHandle(
        name=name,
        pid=os.getpid(),
        hostname=socket.gethostname(),
        started_at=time.time(),
        path=lock_path,
        _fd=fd
    )

    try:
        # Write lock info (without _fd field)
        lock_data = {k: v for k, v in asdict(handle).items() if k != '_fd'}
        lock_data['path'] = str(lock_data['path'])  # Convert Path to string for JSON

        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps(lock_data, indent=2).encode())
        os.fsync(fd)
    except Exception as e:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        raise RuntimeError(f"Failed to write lock metadata: {e}")

    logger.info(f"Acquired lock {name} (PID {handle.pid})")
    return handle


def release(handle: LockHandle) -> None:
    """
    Release lock.

    Args:
        handle: LockHandle from acquire()
    """
    if handle._fd is None:
        logger.warning(f"Lock {handle.name} already released")
        return

    try:
        fcntl.flock(handle._fd, fcntl.LOCK_UN)
        os.close(handle._fd)
        handle._fd = None
        logger.info(f"Released lock {handle.name}")
    except Exception as e:
        logger.error(f"Error releasing lock {handle.name}: {e}")


def is_stale(handle: LockHandle, max_age_s: int = 3600) -> bool:
    """
    Check if lock has exceeded maximum age.

    Args:
        handle: LockHandle to check
        max_age_s: Maximum age in seconds (default 1 hour)

    Returns:
        True if lock is stale
    """
    age = time.time() - handle.started_at
    return age > max_age_s


def reap_stale_locks(max_age_s: int = 3600) -> list[str]:
    """
    Clean up abandoned locks.

    Args:
        max_age_s: Maximum age for a lock (default 1 hour)

    Returns:
        List of reaped lock names
    """
    reaped = []

    if not LOCK_DIR.exists():
        return reaped

    for lock_file in LOCK_DIR.glob("*.lock"):
        try:
            with open(lock_file, 'r') as f:
                lock_data = json.load(f)

            pid = lock_data.get("pid")
            started = lock_data.get("started_at", 0)
            age = time.time() - started

            # Check if process exists
            process_alive = False
            if pid:
                try:
                    os.kill(pid, 0)
                    process_alive = True
                except ProcessLookupError:
                    pass

            # Reap if process is dead or lock is too old
            if not process_alive or age > max_age_s:
                reason = "dead process" if not process_alive else f"age {int(age)}s > {max_age_s}s"
                logger.info(f"Reaping stale lock {lock_file.stem} from PID {pid} ({reason})")
                lock_file.unlink()
                reaped.append(lock_file.stem)

        except Exception as e:
            logger.error(f"Error checking lock {lock_file}: {e}")

    return reaped
