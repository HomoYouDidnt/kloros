import sys
import signal
import logging
from pathlib import Path
from src.spica.service_manager import SPICAServiceManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    if len(sys.argv) < 2 or not sys.argv[1].startswith("--role="):
        print("Usage: python -m src.spica --role=<role-name>")
        sys.exit(1)

    role = sys.argv[1].split("=", 1)[1]
    socket_path = f"/run/spica/spica-{role}.sock"
    registry_path = Path("/var/lib/kloros/spica_registry.json")

    manager = SPICAServiceManager(
        role=role,
        socket_path=socket_path,
        registry_path=registry_path
    )

    def shutdown_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        manager.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    try:
        manager.start()
        logger.info(f"SPICA service {role} running at {socket_path}")

        signal.pause()

    except Exception as e:
        logger.error(f"Service failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
