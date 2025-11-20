# D-REAM Bundle Manifest
Generated: Sat Oct 18 02:55:03 PM EDT 2025
Bundle Location: /home/kloros/D-REAM_BUNDLE/

## Bundle Contents

### Source Code (src/)
- dream/ - Main D-REAM source directory
  - Domain evaluators (CPU, GPU, Memory, Storage, Power/Thermal, etc.)
  - Fitness computation
  - Genetic algorithm implementation
  - Compliance tools
- dream_web_dashboard.py - Flask dashboard for D-REAM monitoring

### Configuration (configs/)
- loop.yaml - Main KLoROS loop configuration with D-REAM settings
- dream_approval_config.json - Approval thresholds
- dream_domain_schedules.json - Domain evaluation schedules
- dream_domain_schedules_daytime.json - Daytime schedule variant
- dream_domain_schedules_overnight.json - Aggressive overnight schedule
- fitness.json - Latest fitness scores

### Artifacts (artifacts/) - 113MB
- domain_evolution/ - Evolution generation records per domain
  - cpu_evolution.jsonl (568 generations)
  - gpu_evolution.jsonl (534 generations)
  - memory_evolution.jsonl
  - storage_evolution.jsonl
  - power_thermal_evolution.jsonl
  - asr_tts_evolution.jsonl
  - audio_evolution.jsonl
  - os_scheduler_evolution.jsonl
  - conversation_evolution.jsonl
- domain_telemetry/ - Raw telemetry events per domain
  - cpu/cpu_telemetry.jsonl (62,179 events)
  - gpu/gpu_telemetry.jsonl (22,814 events)
  - power_thermal/power_thermal_telemetry.jsonl (20,486 events)
  - memory/memory_telemetry.jsonl (15,726 events)
  - asr_tts/asr_tts_telemetry.jsonl (12,697 events)
  - storage/storage_telemetry.jsonl (11,878 events)
  - os_scheduler/os_scheduler_telemetry.jsonl (11,391 events)
  - conversation/conversation_telemetry.jsonl (18,330 events)
- telemetry/events.jsonl - Aggregated events (2,416 entries)
- tool_synthesis_queue.jsonl - Tool synthesis proposals

### Documentation (docs/)
- OVERNIGHT_EVOLUTION.md - Overnight evolution setup documentation
- REALITY_AUDIT_REPORT.md - Comprehensive system audit
- dream_integration_summary.md - Integration documentation
- dream_evolution.md - Evolution system documentation
- audio_dream_status.md - Audio domain status

### Scripts (scripts/)
- morning_report.py - Evolution results analysis script

### Systemd Services (systemd/)
- dream-domains.service - Main D-REAM domain service
- phase-heuristics.service - PHASE heuristics service
- phase-heuristics.timer - PHASE heuristics timer

## Statistics
Total bundle size: 227M
Total files: 631
Total directories: 100

## Key Data Points
- Evolution span: October 8, 2025 - October 18, 2025 (10 days)
- Total telemetry events: 214,440+ lines
- Evolution generations: 568 (CPU), 534 (GPU), etc.
- Domains covered: 9 (CPU, GPU, Memory, Storage, Power/Thermal, ASR/TTS, Audio, OS/Scheduler, Conversation)
