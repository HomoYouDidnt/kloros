#!/usr/bin/env python3
"""
Hardware Exploration Scanner - Autonomous Hardware Discovery

Probes system hardware to discover capabilities, constraints, and optimization opportunities.
Part of KLoROS autonomous curiosity system.

Discovers:
- GPU models, memory, compute capabilities
- Tensor core availability
- VRAM constraints and utilization
- PCIe bandwidth and topology
- CPU capabilities
- Memory constraints
- Hardware-based optimization opportunities

Governance:
- Tool-Integrity: Self-contained, testable, safe probing only
- D-REAM-Allowed-Stack: subprocess, sysfs, /proc parsing
- No destructive operations, read-only exploration
"""

import os
import re
import subprocess
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """Information about a discovered GPU."""
    index: int
    name: str
    vendor: str  # nvidia, amd, intel
    pci_id: str
    memory_total_mb: Optional[int] = None
    memory_used_mb: Optional[int] = None
    memory_free_mb: Optional[int] = None
    compute_capability: Optional[str] = None
    tensor_cores: bool = False
    cuda_available: bool = False
    rocm_available: bool = False
    pcie_gen: Optional[int] = None
    pcie_width: Optional[int] = None


@dataclass
class HardwareCapabilities:
    """Complete hardware capability discovery result."""
    gpus: List[GPUInfo] = field(default_factory=list)
    total_vram_mb: int = 0
    available_vram_mb: int = 0
    cpu_cores: int = 0
    ram_total_mb: int = 0
    ram_available_mb: int = 0
    discovered_at: str = field(default_factory=lambda: __import__('datetime').datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "gpus": [
                {
                    "index": gpu.index,
                    "name": gpu.name,
                    "vendor": gpu.vendor,
                    "pci_id": gpu.pci_id,
                    "memory_total_mb": gpu.memory_total_mb,
                    "memory_used_mb": gpu.memory_used_mb,
                    "memory_free_mb": gpu.memory_free_mb,
                    "compute_capability": gpu.compute_capability,
                    "tensor_cores": gpu.tensor_cores,
                    "cuda_available": gpu.cuda_available,
                    "rocm_available": gpu.rocm_available,
                    "pcie_gen": gpu.pcie_gen,
                    "pcie_width": gpu.pcie_width
                }
                for gpu in self.gpus
            ],
            "total_vram_mb": self.total_vram_mb,
            "available_vram_mb": self.available_vram_mb,
            "cpu_cores": self.cpu_cores,
            "ram_total_mb": self.ram_total_mb,
            "ram_available_mb": self.ram_available_mb,
            "discovered_at": self.discovered_at
        }


class HardwareScanner:
    """Autonomous hardware discovery and exploration."""

    def __init__(self):
        self.capabilities = HardwareCapabilities()

    def scan(self) -> HardwareCapabilities:
        """
        Perform complete hardware scan.

        Returns:
            HardwareCapabilities with all discovered hardware
        """
        logger.info("[hardware_scanner] Starting autonomous hardware discovery")

        self._discover_gpus()
        self._discover_cpu()
        self._discover_memory()
        self._calculate_totals()

        logger.info(f"[hardware_scanner] Discovery complete: {len(self.capabilities.gpus)} GPUs, "
                   f"{self.capabilities.cpu_cores} CPU cores, "
                   f"{self.capabilities.ram_total_mb}MB RAM")

        return self.capabilities

    def _discover_gpus(self) -> None:
        """Discover all GPUs via lspci and additional probing."""
        try:
            # Use lspci to find all display devices
            result = subprocess.run(
                ["lspci", "-nn"],
                capture_output=True,
                text=True,
                timeout=5
            )

            gpu_index = 0
            for line in result.stdout.splitlines():
                # Look for VGA/3D/Display controllers
                if re.search(r"(VGA|3D|Display)", line, re.IGNORECASE):
                    gpu = self._parse_gpu_line(line, gpu_index)
                    if gpu:
                        self.capabilities.gpus.append(gpu)
                        gpu_index += 1
                        logger.info(f"[hardware_scanner] Discovered GPU {gpu.index}: {gpu.name} ({gpu.vendor})")

        except Exception as e:
            logger.warning(f"[hardware_scanner] GPU discovery failed: {e}")

    def _parse_gpu_line(self, line: str, index: int) -> Optional[GPUInfo]:
        """Parse a single lspci line into GPUInfo."""
        try:
            # Extract PCI ID (e.g., "04:00.0")
            pci_match = re.match(r"([0-9a-f:\.]+)\s+", line)
            if not pci_match:
                return None
            pci_id = pci_match.group(1)

            # Determine vendor
            vendor = "unknown"
            if "nvidia" in line.lower():
                vendor = "nvidia"
            elif "amd" in line.lower() or "ati" in line.lower():
                vendor = "amd"
            elif "intel" in line.lower():
                vendor = "intel"

            # Extract GPU name
            # Match pattern like "NVIDIA Corporation GA106 [GeForce RTX 3060 Lite Hash Rate]"
            name_match = re.search(r":\s+(.+?)(?:\s+\[[\w:]+\])?$", line)
            name = name_match.group(1) if name_match else "Unknown GPU"

            gpu = GPUInfo(
                index=index,
                name=name.strip(),
                vendor=vendor,
                pci_id=pci_id
            )

            # Probe additional capabilities
            self._probe_gpu_details(gpu)

            return gpu

        except Exception as e:
            logger.warning(f"[hardware_scanner] Failed to parse GPU line: {e}")
            return None

    def _probe_gpu_details(self, gpu: GPUInfo) -> None:
        """Probe detailed GPU capabilities."""
        # Check for tensor cores based on GPU name/model
        if gpu.vendor == "nvidia":
            # Tensor cores available on Volta (V100), Turing (RTX 20xx), Ampere (RTX 30xx/A100), Ada (RTX 40xx)
            tensor_core_patterns = [
                r"RTX\s+(20|30|40)\d+",  # RTX 2000/3000/4000 series
                r"V100",  # Volta
                r"A100",  # Ampere datacenter
                r"A6000", # Ampere workstation
                r"T4"     # Turing datacenter
            ]
            for pattern in tensor_core_patterns:
                if re.search(pattern, gpu.name, re.IGNORECASE):
                    gpu.tensor_cores = True
                    logger.info(f"[hardware_scanner] GPU {gpu.index} has tensor cores!")
                    break

        # Try to probe VRAM from sysfs (requires proper permissions)
        self._probe_vram(gpu)

        # Try to get PCIe info
        self._probe_pcie(gpu)

        # Check for CUDA/ROCm availability
        if gpu.vendor == "nvidia":
            gpu.cuda_available = self._check_cuda()
        elif gpu.vendor == "amd":
            gpu.rocm_available = self._check_rocm()

    def _probe_vram(self, gpu: GPUInfo) -> None:
        """Attempt to probe VRAM from sysfs or other sources."""
        # Try reading from /sys/class/drm
        try:
            # This is approximate and may not work on all systems
            drm_path = Path(f"/sys/class/drm/card{gpu.index}")
            if drm_path.exists():
                # Try reading memory info if available
                mem_info_path = drm_path / "device" / "mem_info_vram_total"
                if mem_info_path.exists():
                    total_bytes = int(mem_info_path.read_text().strip())
                    gpu.memory_total_mb = total_bytes // (1024 * 1024)
                    logger.info(f"[hardware_scanner] GPU {gpu.index} VRAM: {gpu.memory_total_mb}MB")
        except Exception as e:
            logger.debug(f"[hardware_scanner] Could not probe VRAM for GPU {gpu.index}: {e}")

        # If we couldn't get exact VRAM, estimate based on known models
        if gpu.memory_total_mb is None:
            gpu.memory_total_mb = self._estimate_vram(gpu.name)

    def _estimate_vram(self, gpu_name: str) -> Optional[int]:
        """Estimate VRAM based on known GPU models."""
        vram_estimates = {
            "RTX 3060": 12288,  # 12GB
            "RTX 3070": 8192,   # 8GB
            "RTX 3080": 10240,  # 10GB
            "RTX 3090": 24576,  # 24GB
            "GTX 1080 Ti": 11264,  # 11GB
            "GTX 1080": 8192,   # 8GB
            "RTX 4090": 24576,  # 24GB
        }

        for model, vram_mb in vram_estimates.items():
            if model.lower() in gpu_name.lower():
                logger.info(f"[hardware_scanner] Estimated VRAM for {gpu_name}: {vram_mb}MB")
                return vram_mb

        return None

    def _probe_pcie(self, gpu: GPUInfo) -> None:
        """Probe PCIe generation and width."""
        try:
            # Read from sysfs
            pci_path = Path(f"/sys/bus/pci/devices/0000:{gpu.pci_id}")

            # Current link speed
            link_speed_path = pci_path / "current_link_speed"
            if link_speed_path.exists():
                speed_text = link_speed_path.read_text().strip()
                # Extract generation from speed (e.g., "8.0 GT/s" = PCIe 3.0)
                if "16.0 GT/s" in speed_text or "16 GT/s" in speed_text:
                    gpu.pcie_gen = 4
                elif "8.0 GT/s" in speed_text or "8 GT/s" in speed_text:
                    gpu.pcie_gen = 3
                elif "5.0 GT/s" in speed_text or "5 GT/s" in speed_text:
                    gpu.pcie_gen = 2

            # Current link width
            link_width_path = pci_path / "current_link_width"
            if link_width_path.exists():
                gpu.pcie_width = int(link_width_path.read_text().strip())

            if gpu.pcie_gen and gpu.pcie_width:
                logger.info(f"[hardware_scanner] GPU {gpu.index} PCIe: Gen{gpu.pcie_gen} x{gpu.pcie_width}")

        except Exception as e:
            logger.debug(f"[hardware_scanner] Could not probe PCIe for GPU {gpu.index}: {e}")

    def _check_cuda(self) -> bool:
        """Check if CUDA is available."""
        try:
            # Try running nvidia-smi or checking for CUDA runtime
            result = subprocess.run(
                ["which", "nvcc"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except:
            return False

    def _check_rocm(self) -> bool:
        """Check if ROCm is available."""
        try:
            result = subprocess.run(
                ["which", "rocm-smi"],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except:
            return False

    def _discover_cpu(self) -> None:
        """Discover CPU capabilities."""
        try:
            # Count CPU cores from /proc/cpuinfo
            with open("/proc/cpuinfo", "r") as f:
                cpu_info = f.read()
                # Count processor entries
                self.capabilities.cpu_cores = len(re.findall(r"^processor\s*:", cpu_info, re.MULTILINE))
                logger.info(f"[hardware_scanner] Discovered {self.capabilities.cpu_cores} CPU cores")
        except Exception as e:
            logger.warning(f"[hardware_scanner] CPU discovery failed: {e}")

    def _discover_memory(self) -> None:
        """Discover system memory."""
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        self.capabilities.ram_total_mb = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"):
                        self.capabilities.ram_available_mb = int(line.split()[1]) // 1024

                logger.info(f"[hardware_scanner] RAM: {self.capabilities.ram_total_mb}MB total, "
                           f"{self.capabilities.ram_available_mb}MB available")
        except Exception as e:
            logger.warning(f"[hardware_scanner] Memory discovery failed: {e}")

    def _calculate_totals(self) -> None:
        """Calculate total VRAM across all GPUs."""
        self.capabilities.total_vram_mb = sum(
            gpu.memory_total_mb for gpu in self.capabilities.gpus
            if gpu.memory_total_mb is not None
        )

        self.capabilities.available_vram_mb = sum(
            gpu.memory_free_mb for gpu in self.capabilities.gpus
            if gpu.memory_free_mb is not None
        )

        if self.capabilities.total_vram_mb > 0:
            logger.info(f"[hardware_scanner] Total VRAM: {self.capabilities.total_vram_mb}MB")


def scan_hardware() -> HardwareCapabilities:
    """
    Main entry point for hardware scanning.

    Returns:
        HardwareCapabilities object with all discovered hardware
    """
    scanner = HardwareScanner()
    return scanner.scan()


if __name__ == "__main__":
    # Test hardware scanner
    logging.basicConfig(level=logging.INFO)
    caps = scan_hardware()

    import json
    print(json.dumps(caps.to_dict(), indent=2))
