from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional
import inotify.adapters
import inotify.constants
import threading
import queue
import signal
import logging
import time


class BaseStreamingDaemon(ABC):

    def __init__(
        self,
        watch_path: Path,
        max_queue_size: int = 1000,
        max_workers: int = 2,
        max_cache_size: int = 500
    ):
        self.watch_path = watch_path
        self.event_queue = queue.Queue(maxsize=max_queue_size)
        self.cache: Dict[str, Any] = {}
        self.max_cache_size = max_cache_size
        self.workers = []
        self.max_workers = max_workers
        self.running = False
        self.shutdown_event = threading.Event()
        self.start_time = time.time()

        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def start(self):
        self.running = True
        logging.info(f"[daemon] Starting watch on {self.watch_path}")

        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"worker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        self._watch_files()

    def _watch_files(self):
        watcher = inotify.adapters.InotifyTree(
            str(self.watch_path),
            mask=inotify.constants.IN_MODIFY |
                 inotify.constants.IN_CREATE |
                 inotify.constants.IN_DELETE
        )

        for event in watcher.event_gen(yield_nones=False):
            if self.shutdown_event.is_set():
                break

            (_, type_names, path, filename) = event

            if not filename.endswith('.py'):
                continue

            if 'test_' in filename or '__pycache__' in path:
                continue

            file_path = Path(path) / filename
            event_type = 'modify' if 'IN_MODIFY' in type_names else \
                        'create' if 'IN_CREATE' in type_names else 'delete'

            try:
                self.event_queue.put((event_type, file_path), timeout=1.0)
            except queue.Full:
                logging.warning(f"[daemon] Event queue full, dropping event for {file_path}")

    def _worker_loop(self):
        while not self.shutdown_event.is_set():
            try:
                event_type, file_path = self.event_queue.get(timeout=1.0)

                self.process_file_event(event_type, file_path)

                self.event_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"[daemon] Worker error: {e}", exc_info=True)

    @abstractmethod
    def process_file_event(self, event_type: str, file_path: Path):
        pass

    def _evict_cache_if_needed(self):
        if len(self.cache) > self.max_cache_size:
            to_remove = len(self.cache) - self.max_cache_size
            for key in list(self.cache.keys())[:to_remove]:
                del self.cache[key]

    def _handle_shutdown(self, signum, frame):
        logging.info(f"[daemon] Received signal {signum}, shutting down...")
        self.shutdown_event.set()
        self.running = False

        self.save_state()

    @abstractmethod
    def save_state(self):
        pass

    @abstractmethod
    def load_state(self):
        pass

    def get_health_status(self) -> Dict[str, Any]:
        return {
            'running': self.running,
            'queue_size': self.event_queue.qsize(),
            'cache_size': len(self.cache),
            'uptime': time.time() - self.start_time
        }
