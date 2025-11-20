#!/usr/bin/env python3
"""
GPU Maintenance Lock - System-wide guard for GPU access.

Ensures production VLLM and SPICA canaries never overlap on the GPU.
Uses file-based locking with PID tracking and timeout enforcement.
"""
import os
import time
import logging
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

LOCK_DIR = Path("/home/kloros/.kloros/locks")
GPU_LOCK_FILE = LOCK_DIR / "gpu_maintenance.lock"
ACQUIRE_TIMEOUT = 10  # seconds - abort if can't acquire quickly


@dataclass
class GPULock:
    """Represents an acquired GPU maintenance lock."""
    holder: str  # "vllm-prod" or "spica-canary"
    pid: int
    acquired_at: float
    lock_file: Path

    def release(self):
        """Release the GPU maintenance lock."""
        try:
            if self.lock_file.exists():
                # Verify we still own the lock
                content = self.lock_file.read_text().strip()
                if content.startswith(f"{self.holder}:{self.pid}:"):
                    self.lock_file.unlink()
                    logger.info(f"Released GPU lock: {self.holder} (PID {self.pid})")
                else:
                    logger.warning(f"Lock content mismatch during release: {content}")
        except Exception as e:
            logger.error(f"Failed to release GPU lock: {e}")


def is_process_alive(pid: int) -> bool:
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def try_acquire_gpu_lock(holder: str, timeout_sec: int = ACQUIRE_TIMEOUT) -> Optional[GPULock]:
    """
    Try to acquire the GPU maintenance lock.

    Args:
        holder: Lock holder identifier ("vllm-prod" or "spica-canary")
        timeout_sec: Maximum time to wait for lock acquisition

    Returns:
        GPULock if acquired, None if timeout or failure
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    pid = os.getpid()

    while time.time() - start_time < timeout_sec:
        try:
            # Check if lock exists
            if GPU_LOCK_FILE.exists():
                # Parse existing lock
                content = GPU_LOCK_FILE.read_text().strip()
                parts = content.split(":")
                if len(parts) >= 3:
                    existing_holder = parts[0]
                    existing_pid = int(parts[1])
                    acquired_at = float(parts[2])

                    # Check if lock holder is still alive
                    if not is_process_alive(existing_pid):
                        logger.warning(f"Stale lock found (PID {existing_pid} dead), removing")
                        GPU_LOCK_FILE.unlink()
                        continue  # Try again

                    # Lock is held by active process
                    elapsed = time.time() - acquired_at
                    logger.info(f"GPU lock held by {existing_holder} (PID {existing_pid}) for {elapsed:.1f}s")
                    time.sleep(0.5)
                    continue
                else:
                    logger.warning(f"Malformed lock file, removing: {content}")
                    GPU_LOCK_FILE.unlink()
                    continue

            # Try to create lock atomically
            # Use O_CREAT | O_EXCL to ensure atomicity
            fd = os.open(GPU_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                lock_content = f"{holder}:{pid}:{time.time()}\n"
                os.write(fd, lock_content.encode())
            finally:
                os.close(fd)

            logger.info(f"Acquired GPU lock: {holder} (PID {pid})")
            return GPULock(
                holder=holder,
                pid=pid,
                acquired_at=time.time(),
                lock_file=GPU_LOCK_FILE
            )

        except FileExistsError:
            # Race condition - another process created lock
            time.sleep(0.5)
            continue
        except Exception as e:
            logger.error(f"Failed to acquire GPU lock: {e}")
            time.sleep(0.5)
            continue

    # Timeout
    logger.error(f"Failed to acquire GPU lock within {timeout_sec}s timeout")
    return None


def check_gpu_lock_status() -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Check current GPU lock status without acquiring.

    Returns:
        (is_locked, holder, pid) tuple
    """
    if not GPU_LOCK_FILE.exists():
        return (False, None, None)

    try:
        content = GPU_LOCK_FILE.read_text().strip()
        parts = content.split(":")
        if len(parts) >= 3:
            holder = parts[0]
            pid = int(parts[1])

            # Verify process is alive
            if is_process_alive(pid):
                return (True, holder, pid)
            else:
                # Stale lock
                logger.warning(f"Stale GPU lock detected (PID {pid} dead)")
                return (False, None, None)
    except Exception as e:
        logger.error(f"Failed to check GPU lock status: {e}")

    return (False, None, None)


def force_release_gpu_lock():
    """
    Force release GPU lock (use with caution).

    Should only be used for emergency cleanup or by system admin.
    """
    try:
        if GPU_LOCK_FILE.exists():
            content = GPU_LOCK_FILE.read_text().strip()
            GPU_LOCK_FILE.unlink()
            logger.warning(f"Force released GPU lock: {content}")
    except Exception as e:
        logger.error(f"Failed to force release GPU lock: {e}")
