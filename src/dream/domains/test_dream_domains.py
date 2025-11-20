#!/usr/bin/env python3
"""Test script for D-REAM domain evaluators."""

import sys
sys.path.insert(0, '/home/kloros/src/dream')

from domains.domain_evaluator_base import DomainEvaluator
from domains.cpu_domain_evaluator import CPUDomainEvaluator
from domains.gpu_domain_evaluator import GPUDomainEvaluator
from domains.audio_domain_evaluator import AudioDomainEvaluator
from domains.memory_domain_evaluator import MemoryDomainEvaluator
from domains.storage_domain_evaluator import StorageDomainEvaluator
from domains.asr_tts_domain_evaluator import ASRTTSDomainEvaluator
from domains.power_thermal_domain_evaluator import PowerThermalDomainEvaluator
from domains.os_scheduler_domain_evaluator import OSSchedulerDomainEvaluator

def test_domain_evaluators():
    """Test that all domain evaluators can be instantiated."""

    evaluators = {
        'cpu': CPUDomainEvaluator,
        'gpu': GPUDomainEvaluator,
        'audio': AudioDomainEvaluator,
        'memory': MemoryDomainEvaluator,
        'storage': StorageDomainEvaluator,
        'asr_tts': ASRTTSDomainEvaluator,
        'power_thermal': PowerThermalDomainEvaluator,
        'os_scheduler': OSSchedulerDomainEvaluator
    }

    print("D-REAM Domain Evaluators Status:")
    print("=" * 50)

    loaded = []
    for name, evaluator_class in evaluators.items():
        try:
            evaluator = evaluator_class()
            genome_spec = evaluator.get_genome_spec()
            genome_size = len(genome_spec)
            loaded.append(name)
            print(f"✓ {name:15} - Genome size: {genome_size:3} parameters")
        except Exception as e:
            print(f"✗ {name:15} - Error: {e}")

    print("=" * 50)
    print(f"\nSuccessfully loaded: {len(loaded)}/{len(evaluators)} domain evaluators")
    print(f"Domains ready: {', '.join(loaded)}")

    if len(loaded) == len(evaluators):
        print("\n🚀 All D-REAM domain evaluators are operational!")
        print("The system can now optimize:")
        print("  • CPU performance and power efficiency")
        print("  • GPU compute and LLM inference")
        print("  • Audio pipeline with minimal xruns")
        print("  • DDR5 memory timings and stability")
        print("  • NVMe/SATA storage performance")
        print("  • ASR/TTS accuracy and latency")
        print("  • Power consumption and thermal management")
        print("  • OS kernel and scheduler parameters")
    else:
        print(f"\n⚠️  Some evaluators failed to load")

    return len(loaded) == len(evaluators)

if __name__ == "__main__":
    success = test_domain_evaluators()
    sys.exit(0 if success else 1)