"""
RAG rebuild service for memory system.

Extracted from housekeeping.py - provides RAG database rebuild operations
via external script execution.

This service handles RAG operations that were previously inline in
MemoryHousekeeper, centralizing knowledge base export and rebuild logic.
"""

import re
import sys
import logging
import subprocess
from typing import Any, Dict, Optional

from src.orchestration.core.umn_bus import UMNSub, UMNPub

logger = logging.getLogger(__name__)


class RAGRebuildService:
    """
    RAG rebuild service for episodic memory export and knowledge base rebuild.

    Provides:
    - Export episodic memory summaries to knowledge base
    - Rebuild RAG database from expanded knowledge base

    Can operate as UMN subscriber for agentic housekeeping architecture.
    """

    def __init__(self):
        """Initialize RAG rebuild service."""
        self._umn_sub: Optional[UMNSub] = None
        self._umn_pub: Optional[UMNPub] = None

        self.export_script = "/home/kloros/scripts/export_memory_to_kb.py"
        self.rebuild_script = "/home/kloros/scripts/build_knowledge_base_rag.py"

    def subscribe_to_umn(self) -> None:
        """Subscribe to UMN for agentic housekeeping."""
        self._umn_pub = UMNPub()
        self._umn_sub = UMNSub(
            topic="Q_HOUSEKEEPING.RAG_REBUILD",
            on_json=self._handle_rag_request,
            zooid_name="rag_rebuild_service",
            niche="memory"
        )
        logger.info("[rag_rebuild] Subscribed to Q_HOUSEKEEPING.RAG_REBUILD")

    def _handle_rag_request(self, msg: dict) -> None:
        """Handle UMN request for RAG operations."""
        request_id = msg.get('request_id', 'unknown')
        operation = msg.get('facts', {}).get('operation', 'full')

        try:
            results = {}

            if operation in ('full', 'export'):
                results['export'] = self.export_memory_to_kb()

            if operation in ('full', 'rebuild'):
                results['rebuild'] = self.rebuild_rag_database()

            self._umn_pub.emit(
                signal="Q_HOUSEKEEPING.RAG_REBUILD.COMPLETE",
                ecosystem="memory",
                facts={
                    'request_id': request_id,
                    'success': True,
                    'results': results
                }
            )

        except Exception as e:
            logger.error(f"[rag_rebuild] Error during operation: {e}", exc_info=True)
            if self._umn_pub:
                self._umn_pub.emit(
                    signal="Q_HOUSEKEEPING.RAG_REBUILD.COMPLETE",
                    ecosystem="memory",
                    facts={
                        'request_id': request_id,
                        'success': False,
                        'error': str(e)
                    }
                )

    def export_memory_to_kb(self) -> Dict[str, Any]:
        """
        Export episodic memory summaries to knowledge base for RAG expansion.

        Calls external script: /home/kloros/scripts/export_memory_to_kb.py

        Returns:
            Dictionary with export results:
            - exported: bool
            - summaries_exported: int
            - errors: list
        """
        results = {
            "exported": False,
            "summaries_exported": 0,
            "errors": []
        }

        try:
            result = subprocess.run(
                [sys.executable, self.export_script],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Exported' in line and 'summaries' in line:
                        match = re.search(r'Exported (\d+)', line)
                        if match:
                            results["summaries_exported"] = int(match.group(1))
                results["exported"] = True
                logger.info(f"[rag_rebuild] Exported {results['summaries_exported']} summaries to KB")
            else:
                results["errors"].append(f"Script failed: {result.stderr}")
                logger.error(f"[rag_rebuild] Export failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            results["errors"].append("Export script timed out after 30 seconds")
            logger.error("[rag_rebuild] Export script timed out")
        except FileNotFoundError:
            results["errors"].append(f"Export script not found: {self.export_script}")
            logger.error(f"[rag_rebuild] Export script not found: {self.export_script}")
        except Exception as e:
            results["errors"].append(str(e))
            logger.error(f"[rag_rebuild] Export error: {e}", exc_info=True)

        return results

    def rebuild_rag_database(self) -> Dict[str, Any]:
        """
        Rebuild RAG database from expanded knowledge base.

        Calls external script: /home/kloros/scripts/build_knowledge_base_rag.py

        Returns:
            Dictionary with rebuild results:
            - rebuilt: bool
            - document_count: int
            - errors: list
        """
        results = {
            "rebuilt": False,
            "document_count": 0,
            "errors": []
        }

        try:
            result = subprocess.run(
                [sys.executable, self.rebuild_script],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Total chunks:' in line:
                        match = re.search(r'Total chunks: (\d+)', line)
                        if match:
                            results["document_count"] = int(match.group(1))
                results["rebuilt"] = True
                logger.info(f"[rag_rebuild] Rebuilt RAG with {results['document_count']} chunks")
            else:
                results["errors"].append(f"Script failed: {result.stderr}")
                logger.error(f"[rag_rebuild] Rebuild failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            results["errors"].append("Rebuild script timed out after 120 seconds")
            logger.error("[rag_rebuild] Rebuild script timed out")
        except FileNotFoundError:
            results["errors"].append(f"Rebuild script not found: {self.rebuild_script}")
            logger.error(f"[rag_rebuild] Rebuild script not found: {self.rebuild_script}")
        except Exception as e:
            results["errors"].append(str(e))
            logger.error(f"[rag_rebuild] Rebuild error: {e}", exc_info=True)

        return results

    def shutdown(self) -> None:
        """Close UMN subscriptions."""
        if self._umn_sub:
            self._umn_sub.close()
            logger.info("[rag_rebuild] Closed UMN subscription")
