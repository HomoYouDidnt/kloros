"""
PyPIScanner - Detects missing Python packages.

Compares installed packages against curated lists of useful packages
for different domains (ML, DevOps, monitoring, etc.).
"""

import logging
import subprocess
from typing import List, Set

from .base import CapabilityScanner, CapabilityGap, ScannerMetadata

logger = logging.getLogger(__name__)


class PyPIScanner(CapabilityScanner):
    """Detects missing Python packages that could improve capabilities."""

    ML_PACKAGES = ['torch', 'transformers', 'mlflow', 'wandb']
    DEVOPS_PACKAGES = ['docker', 'kubernetes']
    MONITORING_PACKAGES = ['prometheus-client', 'opentelemetry-api']

    def scan(self) -> List[CapabilityGap]:
        """Scan for missing Python packages."""
        gaps = []

        try:
            installed = self._get_installed_packages()

            all_packages = (
                self.ML_PACKAGES +
                self.DEVOPS_PACKAGES +
                self.MONITORING_PACKAGES
            )

            for pkg in all_packages:
                if pkg not in installed:
                    gaps.append(self._create_gap_for_package(pkg))

            logger.info(f"[pypi_scanner] Found {len(gaps)} missing packages")

        except Exception as e:
            logger.warning(f"[pypi_scanner] Scan failed: {e}")

        return gaps

    def get_metadata(self) -> ScannerMetadata:
        """Return scanner metadata."""
        return ScannerMetadata(
            name='PyPIScanner',
            domain='external_tools',
            alignment_baseline=0.6,
            scan_cost=0.15,
            schedule_weight=0.5  # 0.5 = every 2 hours, 1.0 = every hour
        )

    def _get_installed_packages(self) -> Set[str]:
        """Get set of installed package names."""
        try:
            result = subprocess.run(
                ['pip', 'list', '--format=freeze'],
                capture_output=True,
                text=True,
                timeout=5
            )

            packages = set()
            for line in result.stdout.split('\n'):
                if '==' in line:
                    pkg_name = line.split('==')[0].lower()
                    packages.add(pkg_name)

            return packages

        except Exception as e:
            logger.warning(f"[pypi_scanner] Failed to list packages: {e}")
            return set()

    def _create_gap_for_package(self, pkg: str) -> CapabilityGap:
        """Create CapabilityGap for missing package."""
        if pkg in self.ML_PACKAGES:
            domain = 'machine learning'
            alignment = 0.7
        elif pkg in self.DEVOPS_PACKAGES:
            domain = 'devops'
            alignment = 0.6
        elif pkg in self.MONITORING_PACKAGES:
            domain = 'monitoring'
            alignment = 0.8
        else:
            domain = 'general'
            alignment = 0.5

        return CapabilityGap(
            type='external_tool',
            name=pkg,
            category='pypi_package',
            reason=f"Package {pkg} not installed but commonly used in {domain} work",
            alignment_score=alignment,
            install_cost=0.3,
            metadata={'domain': domain}
        )
