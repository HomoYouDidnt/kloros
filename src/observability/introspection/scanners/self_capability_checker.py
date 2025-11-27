#!/usr/bin/env python3
"""
Self-Capability Checker Scanner

Proactively tests KLoROS's own capabilities and dependencies:
- Can I access my memory store?
- Can I access my vector store?
- Can I read/write files?
- Are my services running?
- Can I reach external dependencies?

Purpose:
Allows KLoROS to self-diagnose before attempting operations.
Prevents cascading failures by detecting broken capabilities
early and surfacing them to introspection.

Example:
Before investigating "Why can't I remember?", check:
"Can I access vector store?" → NO → Qdrant server down
Root cause identified without wasted investigation cycles.
"""

import logging
from typing import Dict, List, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SelfCapabilityChecker:
    """Tests KLoROS's own capabilities and dependencies."""

    def __init__(self):
        self.capabilities = {}
        self.dependency_status = {}

    def check_all_capabilities(self) -> Dict:
        """
        Run all capability checks.

        Returns:
            Dict with:
            - capabilities: {capability_name: status}
            - broken_capabilities: List of failed capabilities
            - dependency_status: {dependency: status}
            - overall_health: 'healthy' | 'degraded' | 'critical'
        """
        logger.info("[self_check] Running capability checks...")

        self.capabilities = {
            'memory_store': self._check_memory_store(),
            'vector_store': self._check_vector_store(),
            'file_system_read': self._check_file_read(),
            'file_system_write': self._check_file_write(),
            'embeddings': self._check_embeddings(),
            'qdrant_server': self._check_qdrant_server(),
            'documentation_catalog': self._check_documentation_catalog(),
            'capability_registry': self._check_capability_registry(),
        }

        broken = [
            name for name, status in self.capabilities.items()
            if not status['available']
        ]

        if len(broken) == 0:
            overall_health = 'healthy'
        elif len(broken) <= 2:
            overall_health = 'degraded'
        else:
            overall_health = 'critical'

        return {
            'capabilities': self.capabilities,
            'broken_capabilities': broken,
            'dependency_status': self.dependency_status,
            'overall_health': overall_health,
            'timestamp': datetime.now().isoformat()
        }

    def _check_memory_store(self) -> Dict:
        """Check if memory store is accessible."""
        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from kloros_memory.storage import MemoryStore

            store = MemoryStore()
            conn = store._get_connection()

            cursor = conn.execute("SELECT COUNT(*) FROM events LIMIT 1")
            count = cursor.fetchone()[0]
            conn.close()

            return {
                'available': True,
                'details': f'{count} events in store',
                'error': None
            }
        except Exception as e:
            return {
                'available': False,
                'details': None,
                'error': str(e)
            }

    def _check_vector_store(self) -> Dict:
        """Check if vector store is accessible."""
        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from kloros_memory.vector_store import get_vector_store

            vector_store = get_vector_store()

            if vector_store is None:
                return {
                    'available': False,
                    'details': None,
                    'error': 'get_vector_store() returned None'
                }

            stats = vector_store.get_stats()

            return {
                'available': True,
                'details': f"{stats.get('document_count', 0)} embeddings",
                'error': None
            }
        except Exception as e:
            return {
                'available': False,
                'details': None,
                'error': str(e)
            }

    def _check_file_read(self) -> Dict:
        """Check if file system read access works."""
        try:
            test_path = Path("/home/kloros/docs")

            if not test_path.exists():
                return {
                    'available': False,
                    'details': None,
                    'error': 'Docs directory not found'
                }

            files = list(test_path.glob("*.md"))

            return {
                'available': True,
                'details': f'{len(files)} markdown files found',
                'error': None
            }
        except Exception as e:
            return {
                'available': False,
                'details': None,
                'error': str(e)
            }

    def _check_file_write(self) -> Dict:
        """Check if file system write access works."""
        try:
            test_file = Path("/tmp/kloros_write_test.txt")

            test_file.write_text("capability check")

            content = test_file.read_text()

            test_file.unlink()

            if content == "capability check":
                return {
                    'available': True,
                    'details': 'Read/write successful',
                    'error': None
                }
            else:
                return {
                    'available': False,
                    'details': None,
                    'error': 'Content mismatch after write'
                }
        except Exception as e:
            return {
                'available': False,
                'details': None,
                'error': str(e)
            }

    def _check_embeddings(self) -> Dict:
        """Check if embedding model is loadable."""
        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from kloros_memory.embeddings import get_embedding_model

            model = get_embedding_model()

            if model is None:
                return {
                    'available': False,
                    'details': None,
                    'error': 'get_embedding_model() returned None'
                }

            test_embedding = model.encode("test")

            return {
                'available': True,
                'details': f'{len(test_embedding)} dim embeddings',
                'error': None
            }
        except Exception as e:
            return {
                'available': False,
                'details': None,
                'error': str(e)
            }

    def _check_qdrant_server(self) -> Dict:
        """Check if Qdrant server is reachable."""
        try:
            import requests

            response = requests.get(
                "http://localhost:6333",
                timeout=2
            )

            if response.status_code == 200:
                return {
                    'available': True,
                    'details': 'Server responding',
                    'error': None
                }
            else:
                return {
                    'available': False,
                    'details': f'HTTP {response.status_code}',
                    'error': 'Non-200 response'
                }
        except Exception as e:
            return {
                'available': False,
                'details': None,
                'error': str(e)
            }

    def _check_documentation_catalog(self) -> Dict:
        """Check if documentation catalog is loadable."""
        try:
            import sys
            sys.path.insert(0, '/home/kloros/src')
            from src.introspection.documentation_catalog import DocumentCatalog

            catalog = DocumentCatalog()

            doc_count = len(catalog.documents)

            return {
                'available': True,
                'details': f'{doc_count} docs cataloged',
                'error': None
            }
        except Exception as e:
            return {
                'available': False,
                'details': None,
                'error': str(e)
            }

    def _check_capability_registry(self) -> Dict:
        """Check if capability registry is accessible."""
        try:
            registry_path = Path("/home/kloros/src/registry/capabilities.yaml")

            if not registry_path.exists():
                return {
                    'available': False,
                    'details': None,
                    'error': 'Registry file not found'
                }

            content = registry_path.read_text()

            import yaml
            data = yaml.safe_load(content)

            capability_count = len(data) if isinstance(data, dict) else 0

            return {
                'available': True,
                'details': f'{capability_count} capabilities registered',
                'error': None
            }
        except Exception as e:
            return {
                'available': False,
                'details': None,
                'error': str(e)
            }

    def format_report(self, results: Dict) -> str:
        """Format capability check results as report."""

        health_icon = {
            'healthy': '✅',
            'degraded': '⚠️',
            'critical': '🔴'
        }.get(results['overall_health'], '❓')

        report = []
        report.append(f"{health_icon} Overall Health: {results['overall_health'].upper()}\n")

        working = []
        broken = []

        for name, status in results['capabilities'].items():
            if status['available']:
                working.append(f"  ✓ {name}: {status['details']}")
            else:
                broken.append(f"  ✗ {name}: {status['error']}")

        if working:
            report.append("Working Capabilities:")
            report.extend(working)

        if broken:
            report.append("\nBroken Capabilities:")
            report.extend(broken)

        if not broken:
            report.append("\n✓ All capabilities functional")

        return '\n'.join(report)

    def suggest_fixes(self, results: Dict) -> List[str]:
        """Suggest fixes for broken capabilities."""

        suggestions = []

        for name, status in results['capabilities'].items():
            if not status['available']:
                error = status['error'].lower() if status['error'] else ''

                if 'qdrant' in name:
                    if 'connection refused' in error:
                        suggestions.append(
                            "Qdrant server not running. Start with: "
                            "cd /home/kloros/config && docker-compose -f qdrant-compose.yml up -d"
                        )
                    elif 'already accessed' in error:
                        suggestions.append(
                            "Qdrant file mode conflict. Switch to server mode in models.toml"
                        )

                elif 'vector_store' in name:
                    suggestions.append(
                        "Vector store unavailable. Check Qdrant server and models.toml configuration"
                    )

                elif 'memory' in name:
                    suggestions.append(
                        "Memory store unavailable. Check /home/kloros/.kloros/memory.db permissions"
                    )

                elif 'file' in name and 'permission' in error:
                    suggestions.append(
                        f"File permission issue for {name}. Run: sudo chown -R kloros:kloros /home/kloros/"
                    )

                elif 'embeddings' in name:
                    suggestions.append(
                        "Embedding model failed to load. Check models.toml and available disk space"
                    )

        return suggestions


def check_self_capabilities() -> Tuple[Dict, str, List[str]]:
    """
    Main entry point: Check all capabilities and return results.

    Returns:
        (results_dict, formatted_report, fix_suggestions)
    """
    checker = SelfCapabilityChecker()
    results = checker.check_all_capabilities()
    report = checker.format_report(results)
    suggestions = checker.suggest_fixes(results)

    return results, report, suggestions


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    results, report, suggestions = check_self_capabilities()

    print(report)

    if suggestions:
        print("\n📋 Suggested Fixes:")
        for idx, suggestion in enumerate(suggestions, 1):
            print(f"{idx}. {suggestion}")
