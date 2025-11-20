"""Fault injection primitives for controlled failures."""

import time
import threading
import os
import random
from typing import Any, Callable, Optional


def inject_timeout(target_obj: Any, route: str, delay_s: float, heal_bus=None, event_source: str = "rag", event_kind: str = "synthesis_timeout"):
    """Wrap target method with artificial sleep.

    Args:
        target_obj: Object containing the method
        route: Method name to wrap
        delay_s: Delay in seconds to inject
        heal_bus: Optional HealBus instance to emit events
        event_source: Event source for heal event
        event_kind: Event kind for heal event
    """
    fn = getattr(target_obj, route, None)
    if fn is None:
        print(f"[injector] Method {route} not found on {target_obj}")
        return

    def wrapped(*a, **kw):
        # Emit heal event when timeout fires
        if heal_bus:
            try:
                from src.self_heal.events import mk_event
                event = mk_event(
                    source=event_source,
                    kind=event_kind,
                    severity="error",
                    route=route,
                    delay_s=delay_s,
                    injected=True
                )
                heal_bus.emit(event)
                print(f"[injector] Emitted heal event: {event_source}.{event_kind}")
            except Exception as e:
                print(f"[injector] Failed to emit heal event: {e}")

        time.sleep(delay_s)
        return fn(*a, **kw)

    setattr(target_obj, route, wrapped)
    print(f"[injector] Timeout {delay_s}s injected into {route}")


def inject_latency_jitter(target_obj: Any, route: str, base_ms: int, jitter_ms: int):
    """Inject variable latency into a method.

    Args:
        target_obj: Object containing the method
        route: Method name to wrap
        base_ms: Base latency in milliseconds
        jitter_ms: Random jitter range in milliseconds
    """
    fn = getattr(target_obj, route, None)
    if fn is None:
        print(f"[injector] Method {route} not found on {target_obj}")
        return

    def wrapped(*a, **kw):
        delay = (base_ms + random.randint(0, jitter_ms)) / 1000.0
        time.sleep(delay)
        return fn(*a, **kw)

    setattr(target_obj, route, wrapped)
    print(f"[injector] Latency jitter {base_ms}±{jitter_ms}ms injected into {route}")


def inject_oom(device: str = "gpu", bytes_req: int = 2_000_000_000):
    """Simulate out-of-memory condition.

    Args:
        device: Device type ("gpu" or "cpu")
        bytes_req: Memory limit in bytes
    """
    os.environ["KLR_FAKE_GPU_LIMIT_BYTES"] = str(bytes_req)
    os.environ["KLR_FAKE_MEM_LIMIT_BYTES"] = str(bytes_req)
    print(f"[injector] OOM constraint set: {device} limited to {bytes_req/1e6:.0f}MB")


def inject_corrupt_file(path: str, bytes_to_flip: int = 64):
    """Corrupt a file by flipping bits.

    Args:
        path: Path to file to corrupt
        bytes_to_flip: Number of bytes to corrupt
    """
    try:
        with open(path, "r+b") as f:
            f.seek(0, 0)
            buf = bytearray(f.read(bytes_to_flip))
            for i in range(len(buf)):
                buf[i] ^= 0xFF
            f.seek(0, 0)
            f.write(buf)
        print(f"[injector] Corrupted {bytes_to_flip} bytes in {path}")
    except Exception as e:
        print(f"[injector] File corruption failed: {e}")


def inject_deadlock(lock_a: threading.Lock, lock_b: threading.Lock):
    """Create classic AB-BA deadlock in background threads.

    Args:
        lock_a: First lock
        lock_b: Second lock
    """
    def t1():
        with lock_a:
            time.sleep(0.05)
            with lock_b:
                pass

    def t2():
        with lock_b:
            time.sleep(0.05)
            with lock_a:
                pass

    threading.Thread(target=t1, daemon=True).start()
    threading.Thread(target=t2, daemon=True).start()
    print("[injector] Deadlock injected (AB-BA)")


def inject_quota_exceeded(service: str = "tool_synth"):
    """Simulate quota/rate limit exceeded.

    Args:
        service: Service name for quota flag
    """
    os.environ["KLR_FORCE_QUOTA_EXCEEDED"] = "1"
    os.environ[f"KLR_QUOTA_EXCEEDED_{service.upper()}"] = "1"
    print(f"[injector] Quota exceeded flag set for {service}")


def inject_exception(target_obj: Any, route: str, exception_type: type, message: str = "Injected failure"):
    """Make a method raise an exception.

    Args:
        target_obj: Object containing the method
        route: Method name to wrap
        exception_type: Exception class to raise
        message: Exception message
    """
    fn = getattr(target_obj, route, None)
    if fn is None:
        print(f"[injector] Method {route} not found on {target_obj}")
        return

    def wrapped(*a, **kw):
        raise exception_type(message)

    setattr(target_obj, route, wrapped)
    print(f"[injector] Exception {exception_type.__name__} injected into {route}")


def inject_slow_io(path: str, delay_s: float = 1.0):
    """Slow down file I/O operations.

    Args:
        path: File path pattern to slow
        delay_s: Delay per operation in seconds
    """
    os.environ["KLR_SLOW_IO_PATH"] = path
    os.environ["KLR_SLOW_IO_DELAY"] = str(delay_s)
    print(f"[injector] Slow I/O injected for {path}: {delay_s}s delay")


def inject_intermittent_failure(target_obj: Any, route: str, fail_rate: float = 0.3, heal_bus=None, event_source: str = "rag", event_kind: str = "synthesis_timeout"):
    """Make a method fail intermittently.

    Args:
        target_obj: Object containing the method
        route: Method name to wrap
        fail_rate: Probability of failure (0.0-1.0)
        heal_bus: Optional HealBus instance to emit events
        event_source: Event source for heal event
        event_kind: Event kind for heal event
    """
    fn = getattr(target_obj, route, None)
    if fn is None:
        print(f"[injector] Method {route} not found on {target_obj}")
        return

    def wrapped(*a, **kw):
        if random.random() < fail_rate:
            # Emit heal event when failure occurs
            if heal_bus:
                try:
                    from src.self_heal.events import mk_event
                    event = mk_event(
                        source=event_source,
                        kind=event_kind,
                        severity="error",
                        route=route,
                        fail_rate=fail_rate,
                        injected=True
                    )
                    heal_bus.emit(event)
                    print(f"[injector] Emitted heal event: {event_source}.{event_kind}")
                except Exception as e:
                    print(f"[injector] Failed to emit heal event: {e}")

            raise RuntimeError(f"Intermittent failure in {route}")
        return fn(*a, **kw)

    setattr(target_obj, route, wrapped)
    print(f"[injector] Intermittent failure ({fail_rate*100:.0f}%) injected into {route}")
