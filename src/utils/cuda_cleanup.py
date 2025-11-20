"""CUDA memory cleanup utilities for KLoROS."""

import atexit
import gc
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def teardown_model(model: Any, extra_tensors: Optional[List[Any]] = None) -> None:
    """Safely teardown CUDA model and free memory."""
    try:
        if extra_tensors:
            for tensor in extra_tensors:
                try:
                    del tensor
                except Exception:
                    pass

        if model is not None:
            del model

    except Exception as e:
        logger.warning(f"Error during model teardown: {e}")

    cleanup_cuda()


def cleanup_cuda() -> None:
    """Clean up CUDA memory and contexts."""
    try:
        import sys
        if "torch" in sys.modules:
            import torch

            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                logger.debug("CUDA memory cleared")

        gc.collect()

    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Error during CUDA cleanup: {e}")


def setup_graceful_shutdown() -> None:
    """Setup graceful shutdown handlers for CUDA cleanup."""

    def shutdown_handler():
        logger.info("Performing graceful CUDA cleanup on shutdown")
        cleanup_cuda()

    atexit.register(shutdown_handler)

    import signal

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, cleaning up...")
        shutdown_handler()
        signal.default_int_handler(signum, frame)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def setup_multiprocessing_spawn() -> None:
    """Configure multiprocessing to use spawn instead of fork."""
    try:
        import multiprocessing as mp

        if mp.get_start_method(allow_none=True) != "spawn":
            mp.set_start_method("spawn", force=True)
            logger.info("Multiprocessing configured to use spawn method")

    except RuntimeError as e:
        logger.debug(f"Multiprocessing start method already set: {e}")
    except Exception as e:
        logger.warning(f"Error configuring multiprocessing: {e}")


def safe_cuda_init() -> None:
    """Safely initialize CUDA environment."""
    try:
        setup_multiprocessing_spawn()
        setup_graceful_shutdown()

        import sys
        if "torch" in sys.modules:
            import torch
            if torch.cuda.is_available():
                logger.info(f"CUDA initialized - devices: {torch.cuda.device_count()}")

    except ImportError:
        logger.debug("PyTorch not available, skipping CUDA initialization")
    except Exception as e:
        logger.warning(f"Error during CUDA initialization: {e}")


if __name__ != "__main__":
    safe_cuda_init()
