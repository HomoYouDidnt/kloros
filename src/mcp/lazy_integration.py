"""
Lazy-loading MCP integration wrapper.

Reduces memory footprint by:
- Loading servers on-demand
- Unloading idle servers after timeout
- Keeping capability graph in memory (lightweight)
- Pooling frequently-used servers
"""
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from collections import defaultdict
from datetime import datetime

from .integration import MCPIntegration, RoutingDecision
from .client import MCPClient, MCPServer

logger = logging.getLogger(__name__)

IDLE_TIMEOUT_S = 300
POOL_SIZE = 5


class LazyMCPIntegration:
    """
    Memory-efficient MCP integration with lazy loading and idle unloading.
    """

    def __init__(
        self,
        manifest_dir: str = "/home/kloros/src/mcp/manifests",
        idle_timeout_s: int = IDLE_TIMEOUT_S,
        pool_size: int = POOL_SIZE
    ):
        self.manifest_dir = Path(manifest_dir)
        self.idle_timeout_s = idle_timeout_s
        self.pool_size = pool_size

        self.client = MCPClient()
        self.active_servers: Dict[str, MCPServer] = {}
        self.server_last_used: Dict[str, float] = defaultdict(float)
        self.server_use_count: Dict[str, int] = defaultdict(int)

        manifests = list(self.manifest_dir.glob("*.json"))
        logger.info(f"[lazy-mcp] Discovered {len(manifests)} server manifests (not loaded)")

    def get_server(self, server_id: str) -> Optional[MCPServer]:
        """
        Get server, loading it if necessary.

        Args:
            server_id: Server to retrieve

        Returns:
            MCPServer instance or None if not found
        """
        now = time.time()

        if server_id in self.active_servers:
            self.server_last_used[server_id] = now
            self.server_use_count[server_id] += 1
            return self.active_servers[server_id]

        manifest_path = self.manifest_dir / f"{server_id}.json"
        if not manifest_path.exists():
            logger.warning(f"[lazy-mcp] Manifest not found: {server_id}")
            return None

        logger.info(f"[lazy-mcp] Loading server: {server_id}")
        try:
            server = self.client.load_server(str(manifest_path))
            self.active_servers[server_id] = server
            self.server_last_used[server_id] = now
            self.server_use_count[server_id] = 1

            self._enforce_pool_limit()
            return server

        except Exception as e:
            logger.error(f"[lazy-mcp] Failed to load {server_id}: {e}")
            return None

    def _enforce_pool_limit(self):
        """
        Unload least-recently-used servers if pool size exceeded.
        """
        if len(self.active_servers) <= self.pool_size:
            return

        servers_by_lru = sorted(
            self.active_servers.keys(),
            key=lambda s: self.server_last_used[s]
        )

        to_unload = servers_by_lru[: len(self.active_servers) - self.pool_size]

        for server_id in to_unload:
            logger.info(f"[lazy-mcp] Unloading idle server: {server_id}")
            del self.active_servers[server_id]

    def prune_idle_servers(self):
        """
        Unload servers that haven't been used within idle_timeout_s.
        """
        now = time.time()
        to_unload = []

        for server_id, last_used in self.server_last_used.items():
            if server_id in self.active_servers and (now - last_used) > self.idle_timeout_s:
                to_unload.append(server_id)

        for server_id in to_unload:
            logger.info(f"[lazy-mcp] Pruning idle server: {server_id} (idle for {self.idle_timeout_s}s)")
            del self.active_servers[server_id]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get memory and usage statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "active_servers": len(self.active_servers),
            "total_manifests": len(list(self.manifest_dir.glob("*.json"))),
            "pool_size": self.pool_size,
            "idle_timeout_s": self.idle_timeout_s,
            "use_counts": dict(self.server_use_count),
            "most_used": max(self.server_use_count.items(), key=lambda x: x[1]) if self.server_use_count else None
        }


def create_lazy_mcp(
    manifest_dir: str = "/home/kloros/src/mcp/manifests",
    idle_timeout_s: int = IDLE_TIMEOUT_S,
    pool_size: int = POOL_SIZE
) -> LazyMCPIntegration:
    """
    Factory function for creating lazy MCP integration.
    """
    return LazyMCPIntegration(
        manifest_dir=manifest_dir,
        idle_timeout_s=idle_timeout_s,
        pool_size=pool_size
    )
