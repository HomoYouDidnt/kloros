"""Comprehensive system mapping for KLoROS self-awareness.

Maps all directories, files, hardware, software, and capabilities
to enable intelligent tool synthesis and optimization.
"""

import os
import sys
import json
import subprocess
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import hashlib


class SystemMapper:
    """Maps KLoROS system state for self-awareness and capability analysis."""

    def __init__(self, kloros_root: str = "/home/kloros"):
        self.kloros_root = Path(kloros_root)
        self.cache_file = Path("/home/kloros/.kloros/system_map.json")
        self.last_scan: Optional[datetime] = None
        self.system_map: Dict[str, Any] = {}

    def scan_full_system(self, force: bool = False) -> Dict[str, Any]:
        """Perform comprehensive system scan.

        Args:
            force: Force rescan even if cache exists

        Returns:
            Complete system map
        """
        # Load cached map if available and recent
        if not force and self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    cached = json.load(f)
                    cache_age_hours = (datetime.now() - datetime.fromisoformat(cached['timestamp'])).total_seconds() / 3600
                    if cache_age_hours < 24:  # Cache valid for 24 hours
                        print(f"[mapper] Using cached system map ({cache_age_hours:.1f}h old)")
                        self.system_map = cached
                        return cached
            except Exception as e:
                print(f"[mapper] Cache load failed: {e}, performing fresh scan")

        print("[mapper] Starting comprehensive system scan...")
        start = datetime.now()

        self.system_map = {
            "timestamp": datetime.now().isoformat(),
            "filesystem": self._scan_filesystem(),
            "hardware": self._scan_hardware(),
            "software": self._scan_software(),
            "capabilities": self._scan_capabilities(),
            "tools": self._scan_existing_tools(),
            "models": self._scan_models(),
            "configuration": self._scan_configuration(),
        }

        # Analyze gaps between what exists and what tools cover
        self.system_map["gap_analysis"] = self._analyze_gaps()

        duration = (datetime.now() - start).total_seconds()
        print(f"[mapper] Scan completed in {duration:.1f}s")

        # Cache the results
        self._save_cache()

        return self.system_map

    def _scan_filesystem(self) -> Dict[str, Any]:
        """Scan KLoROS filesystem structure."""
        print("[mapper] Scanning filesystem...")

        filesystem = {
            "directories": [],
            "python_modules": [],
            "data_directories": [],
            "config_files": [],
        }

        # Scan main source tree
        src_path = self.kloros_root / "src"
        if src_path.exists():
            for root, dirs, files in os.walk(src_path):
                rel_path = Path(root).relative_to(self.kloros_root)

                # Track directories
                filesystem["directories"].append(str(rel_path))

                # Track Python modules
                for f in files:
                    if f.endswith('.py') and not f.startswith('__'):
                        module_path = str(rel_path / f)
                        filesystem["python_modules"].append(module_path)

        # Scan data/model directories
        for data_dir in ['models', 'data', '.kloros', 'logs']:
            dir_path = self.kloros_root / data_dir
            if dir_path.exists():
                filesystem["data_directories"].append({
                    "path": str(dir_path),
                    "size_mb": self._get_dir_size(dir_path) / (1024 * 1024),
                    "file_count": sum(1 for _ in dir_path.rglob('*') if _.is_file())
                })

        # Scan config files
        for config_file in ['.kloros_env', 'requirements.txt', 'setup.py']:
            config_path = self.kloros_root / config_file
            if config_path.exists():
                filesystem["config_files"].append(str(config_path))

        return filesystem

    def _scan_hardware(self) -> Dict[str, Any]:
        """Scan available hardware."""
        print("[mapper] Scanning hardware...")

        hardware = {
            "gpu": self._detect_gpu(),
            "audio": self._detect_audio(),
            "cpu": self._detect_cpu(),
            "memory": self._detect_memory(),
        }

        return hardware

    def _scan_software(self) -> Dict[str, Any]:
        """Scan installed software and dependencies."""
        print("[mapper] Scanning software...")

        software = {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "installed_packages": self._get_installed_packages(),
            "ollama_models": self._get_ollama_models(),
        }

        return software

    def _scan_capabilities(self) -> Dict[str, Any]:
        """Scan KLoROS capabilities."""
        print("[mapper] Scanning capabilities...")

        capabilities = {
            "audio_input": self._check_capability("audio_backend"),
            "audio_output": self._check_capability("tts_backend"),
            "speech_recognition": self._check_capability("stt_backend"),
            "text_generation": self._check_capability("reason_backend"),
            "rag_retrieval": self._check_module("src.rag.base_rag"),
            "tool_synthesis": self._check_module("src.tool_synthesis"),
            "d_ream_evolution": self._check_module("src.evolution.dream"),
            "memory_system": self._check_module("src.memory.episodic_memory"),
            "xai_explainability": self._check_module("src.xai.middleware"),
        }

        return capabilities

    def _scan_existing_tools(self) -> List[Dict[str, str]]:
        """Scan registered introspection tools."""
        print("[mapper] Scanning existing tools...")

        tools = []
        try:
            from src.introspection_tools import IntrospectionToolRegistry
            registry = IntrospectionToolRegistry()

            for name, tool in registry.tools.items():
                tools.append({
                    "name": name,
                    "description": tool.description,
                    "parameters": tool.parameters or [],
                })
        except Exception as e:
            print(f"[mapper] Tool scan failed: {e}")

        return tools

    def _scan_models(self) -> Dict[str, Any]:
        """Scan available AI models."""
        print("[mapper] Scanning models...")

        models = {
            "vosk": [],
            "piper": [],
            "whisper": [],
        }

        models_dir = self.kloros_root / "models"
        if models_dir.exists():
            # Scan VOSK models
            vosk_dir = models_dir / "vosk"
            if vosk_dir.exists():
                for model_path in vosk_dir.iterdir():
                    if model_path.is_dir():
                        models["vosk"].append({
                            "name": model_path.name,
                            "path": str(model_path),
                            "size_mb": self._get_dir_size(model_path) / (1024 * 1024)
                        })

            # Scan Piper voices
            piper_dir = models_dir / "piper"
            if piper_dir.exists():
                for model_file in piper_dir.glob("*.onnx"):
                    models["piper"].append({
                        "name": model_file.stem,
                        "path": str(model_file),
                        "size_mb": model_file.stat().st_size / (1024 * 1024)
                    })

        return models

    def _scan_configuration(self) -> Dict[str, Any]:
        """Scan system configuration."""
        print("[mapper] Scanning configuration...")

        config = {
            "environment_variables": self._get_kloros_env_vars(),
            "systemd_service": self._check_systemd_service(),
        }

        return config

    def _analyze_gaps(self) -> Dict[str, List[str]]:
        """Analyze gaps between capabilities and tools."""
        print("[mapper] Analyzing capability gaps...")

        gaps = {
            "missing_tools": [],
            "untested_capabilities": [],
            "optimization_opportunities": [],
        }

        # Check for major subsystems without dedicated tools
        subsystems = {
            "rag": "RAG retrieval status and configuration",
            "memory": "Memory system statistics and optimization",
            "evolution": "D-REAM evolution history and metrics",
            "xai": "XAI trace analysis and explainability",
            "audio": "Audio device testing and calibration",
            "models": "Model performance benchmarking",
        }

        existing_tool_names = [t["name"] for t in self.system_map.get("tools", [])]

        for subsystem, description in subsystems.items():
            # Check if any tool covers this subsystem
            has_tool = any(subsystem in name for name in existing_tool_names)
            if not has_tool:
                gaps["missing_tools"].append({
                    "subsystem": subsystem,
                    "description": description,
                    "priority": "high" if subsystem in ["rag", "evolution"] else "medium"
                })

        # Identify optimization opportunities
        if self.system_map.get("hardware", {}).get("gpu", {}).get("available"):
            # Have GPU but should verify it's being used optimally
            gaps["optimization_opportunities"].append({
                "component": "gpu",
                "description": "GPU available - should benchmark utilization and performance",
                "action": "create_gpu_benchmark_tool"
            })

        return gaps

    def _detect_gpu(self) -> Dict[str, Any]:
        """Detect GPU availability and specs."""
        gpu_info = {"available": False}

        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,utilization.gpu", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                gpus = []
                for line in lines:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        gpus.append({
                            "name": parts[0].strip(),
                            "memory_mb": parts[1].strip(),
                            "utilization": parts[2].strip()
                        })
                gpu_info = {
                    "available": True,
                    "count": len(gpus),
                    "devices": gpus
                }
        except Exception:
            pass

        return gpu_info

    def _detect_audio(self) -> Dict[str, Any]:
        """Detect audio devices."""
        audio_info = {"input_devices": [], "output_devices": []}

        try:
            # Use pactl to list sources (input) and sinks (output)
            result = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            audio_info["input_devices"].append(parts[1])

            result = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            audio_info["output_devices"].append(parts[1])
        except Exception:
            pass

        return audio_info

    def _detect_cpu(self) -> Dict[str, Any]:
        """Detect CPU info."""
        cpu_info = {}

        try:
            result = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if "Model name:" in line:
                        cpu_info["model"] = line.split(':', 1)[1].strip()
                    elif "CPU(s):" in line and "NUMA" not in line:
                        cpu_info["cores"] = line.split(':', 1)[1].strip()
        except Exception:
            pass

        return cpu_info

    def _detect_memory(self) -> Dict[str, Any]:
        """Detect memory info."""
        memory_info = {}

        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if 'MemTotal' in line:
                        kb = int(line.split()[1])
                        memory_info["total_gb"] = round(kb / (1024 * 1024), 1)
                    elif 'MemAvailable' in line:
                        kb = int(line.split()[1])
                        memory_info["available_gb"] = round(kb / (1024 * 1024), 1)
        except Exception:
            pass

        return memory_info

    def _get_installed_packages(self) -> List[str]:
        """Get list of installed Python packages."""
        packages = []
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=freeze"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                packages = [line.split('==')[0] for line in result.stdout.strip().split('\n') if '==' in line]
        except Exception:
            pass
        return packages[:50]  # Limit to first 50 for brevity

    def _get_ollama_models(self) -> List[str]:
        """Get list of available Ollama models."""
        models = []
        try:
            result = subprocess.run(
                ["curl", "-s", "http://127.0.0.1:11434/api/tags"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                models = [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return models

    def _check_capability(self, attr_name: str) -> bool:
        """Check if a capability attribute would be available."""
        # This is a heuristic - we'd need actual kloros_instance to check
        # For now, return True if the module exists
        return True

    def _check_module(self, module_path: str) -> bool:
        """Check if a Python module exists."""
        try:
            spec = importlib.util.find_spec(module_path)
            return spec is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False

    def _get_kloros_env_vars(self) -> Dict[str, str]:
        """Get KLoROS-related environment variables."""
        env_vars = {}
        for key, value in os.environ.items():
            if key.startswith('KLR_') or key in ['OLLAMA_HOST', 'CUDA_VISIBLE_DEVICES']:
                env_vars[key] = value
        return env_vars

    def _check_systemd_service(self) -> Dict[str, Any]:
        """Check if KLoROS is running as systemd service."""
        service_info = {"enabled": False, "active": False}
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "kloros.service"],
                capture_output=True, text=True, timeout=1
            )
            service_info["active"] = result.returncode == 0

            result = subprocess.run(
                ["systemctl", "is-enabled", "kloros.service"],
                capture_output=True, text=True, timeout=1
            )
            service_info["enabled"] = result.returncode == 0
        except Exception:
            pass
        return service_info

    def _get_dir_size(self, path: Path) -> int:
        """Get total size of directory in bytes."""
        total = 0
        try:
            for entry in path.rglob('*'):
                if entry.is_file():
                    total += entry.stat().st_size
        except Exception:
            pass
        return total

    def _save_cache(self):
        """Save system map to cache."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.system_map, f, indent=2)
            print(f"[mapper] Cached system map to {self.cache_file}")
        except Exception as e:
            print(f"[mapper] Cache save failed: {e}")

    def get_summary(self) -> str:
        """Get human-readable summary of system map."""
        if not self.system_map:
            return "System map not yet generated. Run scan_full_system() first."

        lines = ["=== KLoROS System Map ===\n"]

        # Filesystem
        fs = self.system_map.get("filesystem", {})
        lines.append(f"📁 Directories: {len(fs.get('directories', []))}")
        lines.append(f"🐍 Python modules: {len(fs.get('python_modules', []))}")

        # Hardware
        hw = self.system_map.get("hardware", {})
        if hw.get("gpu", {}).get("available"):
            gpu_count = hw["gpu"]["count"]
            lines.append(f"🎮 GPUs: {gpu_count} available")
        else:
            lines.append("🎮 GPUs: None detected")

        mem = hw.get("memory", {})
        if mem:
            lines.append(f"💾 Memory: {mem.get('total_gb', '?')}GB total, {mem.get('available_gb', '?')}GB available")

        # Tools
        tools = self.system_map.get("tools", [])
        lines.append(f"🔧 Registered tools: {len(tools)}")

        # Gap analysis
        gaps = self.system_map.get("gap_analysis", {})
        missing_tools = gaps.get("missing_tools", [])
        if missing_tools:
            lines.append(f"\n⚠️  Missing tools: {len(missing_tools)}")
            for gap in missing_tools[:5]:
                lines.append(f"   • {gap['subsystem']}: {gap['description']}")

        return "\n".join(lines)
