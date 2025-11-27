"""Smart GPU management for hybrid ASR system."""

from __future__ import annotations

import os
import warnings
from typing import Dict, List, Optional, Tuple, Union


class GPUManager:
    """Manages GPU allocation for VOSK-Whisper hybrid system."""
    
    def __init__(self):
        """Initialize GPU manager."""
        self.available_gpus = self._detect_gpus()
        self.gpu_assignments = {}
        self.gpu_memory_usage = {}
        
    def _detect_gpus(self) -> List[Dict]:
        """Detect available GPUs and their capabilities.
        
        Returns:
            List of GPU information dictionaries
        """
        gpus = []
        
        try:
            import torch
            if torch.cuda.is_available():
                for i in range(torch.cuda.device_count()):
                    gpu_props = torch.cuda.get_device_properties(i)
                    gpu_info = {
                        "device_id": i,
                        "name": gpu_props.name,
                        "memory_total": gpu_props.total_memory,
                        "memory_free": torch.cuda.mem_get_info(i)[0] if torch.cuda.is_available() else 0,
                        "compute_capability": f"{gpu_props.major}.{gpu_props.minor}",
                        "is_compatible": gpu_props.major >= 6,  # Minimum for modern workloads
                        "recommended_for": self._get_gpu_recommendation(gpu_props),
                    }
                    gpus.append(gpu_info)
                    
        except ImportError:
            warnings.warn("PyTorch not available, GPU detection limited")
        except Exception as e:
            warnings.warn(f"GPU detection failed: {e}")
            
        return gpus
    
    def _get_gpu_recommendation(self, gpu_props) -> str:
        """Get recommendation for GPU usage based on properties.
        
        Args:
            gpu_props: PyTorch GPU properties
            
        Returns:
            Recommendation string
        """
        # RTX 3060 and newer - primary processing
        if "RTX 30" in gpu_props.name or "RTX 40" in gpu_props.name:
            return "primary_whisper"
        
        # GTX 1080 Ti and similar - secondary processing
        elif "GTX 1080" in gpu_props.name or "GTX 1070" in gpu_props.name:
            return "secondary_tasks"
        
        # Older or lower-end GPUs - basic tasks only
        elif gpu_props.total_memory < 4 * 1024**3:  # Less than 4GB
            return "basic_tasks"
        
        # Default for unknown modern GPUs
        elif gpu_props.major >= 7:  # Volta and newer
            return "primary_whisper"
        
        else:
            return "secondary_tasks"
    
    def assign_optimal_configuration(
        self, 
        enable_dual_gpu: bool = True,
        memory_limit_mb: Optional[int] = None
    ) -> Dict[str, Union[int, str]]:
        """Assign optimal GPU configuration for hybrid ASR.
        
        Args:
            enable_dual_gpu: Whether to use multiple GPUs if available
            memory_limit_mb: Memory limit per GPU in MB
            
        Returns:
            Dictionary with GPU assignments
        """
        config = {
            "whisper_device": "cpu",
            "whisper_device_index": 0,
            "secondary_device": "cpu",
            "secondary_device_index": 0,
            "strategy": "cpu_only",
        }
        
        if not self.available_gpus:
            return config
        
        # Sort GPUs by recommendation priority
        primary_gpus = [gpu for gpu in self.available_gpus if gpu["recommended_for"] == "primary_whisper"]
        secondary_gpus = [gpu for gpu in self.available_gpus if gpu["recommended_for"] == "secondary_tasks"]
        
        if primary_gpus:
            # Use best primary GPU for Whisper
            best_primary = max(primary_gpus, key=lambda x: x["memory_total"])
            config["whisper_device"] = "cuda"
            config["whisper_device_index"] = best_primary["device_id"]
            
            if enable_dual_gpu and secondary_gpus:
                # Use secondary GPU for other tasks
                best_secondary = max(secondary_gpus, key=lambda x: x["memory_total"])
                config["secondary_device"] = "cuda"
                config["secondary_device_index"] = best_secondary["device_id"]
                config["strategy"] = "dual_gpu"
            else:
                config["strategy"] = "single_gpu"
                
        elif secondary_gpus and not primary_gpus:
            # Only secondary GPUs available - use best one for Whisper
            best_secondary = max(secondary_gpus, key=lambda x: x["memory_total"])
            config["whisper_device"] = "cuda"
            config["whisper_device_index"] = best_secondary["device_id"]
            config["strategy"] = "single_gpu_secondary"
        
        return config
    
    def get_memory_info(self, device_id: int) -> Dict[str, int]:
        """Get memory information for a specific GPU.
        
        Args:
            device_id: GPU device ID
            
        Returns:
            Dictionary with memory information
        """
        try:
            import torch
            if torch.cuda.is_available() and device_id < torch.cuda.device_count():
                free, total = torch.cuda.mem_get_info(device_id)
                used = total - free
                return {
                    "total": total,
                    "free": free,
                    "used": used,
                    "usage_percent": (used / total) * 100 if total > 0 else 0,
                }
        except Exception as e:
            warnings.warn(f"Failed to get memory info for GPU {device_id}: {e}")
        
        return {"total": 0, "free": 0, "used": 0, "usage_percent": 0}
    
    def suggest_whisper_settings(self, device_id: int) -> Dict[str, Union[str, int]]:
        """Suggest optimal Whisper settings for a specific GPU.
        
        Args:
            device_id: GPU device ID
            
        Returns:
            Dictionary with suggested settings
        """
        if device_id >= len(self.available_gpus):
            return {"model_size": "small", "compute_type": "int8", "device": "cpu"}
        
        gpu_info = self.available_gpus[device_id]
        memory_gb = gpu_info["memory_total"] / (1024**3)
        
        if memory_gb >= 8:  # 8GB+ VRAM
            return {
                "model_size": "medium",
                "compute_type": "int8_float16",
                "device": "cuda",
                "batch_size": 16,
            }
        elif memory_gb >= 6:  # 6-8GB VRAM
            return {
                "model_size": "small",
                "compute_type": "int8_float16",
                "device": "cuda",
                "batch_size": 8,
            }
        elif memory_gb >= 4:  # 4-6GB VRAM
            return {
                "model_size": "small",
                "compute_type": "int8",
                "device": "cuda",
                "batch_size": 4,
            }
        else:  # Less than 4GB VRAM
            return {
                "model_size": "tiny",
                "compute_type": "int8",
                "device": "cuda",
                "batch_size": 2,
            }
    
    def monitor_gpu_health(self) -> Dict[int, Dict]:
        """Monitor GPU health and performance.
        
        Returns:
            Dictionary with GPU health information
        """
        health_info = {}
        
        for gpu in self.available_gpus:
            device_id = gpu["device_id"]
            memory_info = self.get_memory_info(device_id)
            
            health_info[device_id] = {
                "name": gpu["name"],
                "memory_usage_percent": memory_info["usage_percent"],
                "memory_free_gb": memory_info["free"] / (1024**3),
                "status": "healthy" if memory_info["usage_percent"] < 90 else "high_usage",
                "recommendation": gpu["recommended_for"],
            }
        
        return health_info
    
    def get_system_report(self) -> Dict:
        """Get comprehensive system report.
        
        Returns:
            Dictionary with system information
        """
        return {
            "gpu_count": len(self.available_gpus),
            "gpus": self.available_gpus,
            "optimal_config": self.assign_optimal_configuration(),
            "gpu_health": self.monitor_gpu_health(),
            "recommendations": self._generate_recommendations(),
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate performance recommendations.
        
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        if len(self.available_gpus) == 0:
            recommendations.append("No GPUs detected - using CPU mode")
        elif len(self.available_gpus) == 1:
            recommendations.append("Single GPU detected - consider CPU fallback for reliability")
        elif len(self.available_gpus) >= 2:
            recommendations.append("Multiple GPUs detected - enabling dual-GPU strategy")
        
        for gpu in self.available_gpus:
            memory_gb = gpu["memory_total"] / (1024**3)
            if memory_gb < 4:
                recommendations.append(f"GPU {gpu['device_id']} ({gpu['name']}) has limited VRAM - consider CPU mode")
            elif memory_gb >= 8:
                recommendations.append(f"GPU {gpu['device_id']} ({gpu['name']}) well-suited for large Whisper models")
        
        return recommendations
