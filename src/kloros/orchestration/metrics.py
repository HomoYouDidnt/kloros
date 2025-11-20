from prometheus_client import Counter, Gauge, Histogram

# Orchestrator core metrics
orchestrator_tick_total = Counter("kloros_orchestrator_tick_total", "Total orchestrator ticks", ["outcome"])
orchestrator_lock_contention = Counter("kloros_orchestrator_lock_contention", "Lock contention events")

# PHASE metrics
phase_runs_total = Counter("kloros_phase_runs_total", "Total PHASE runs", ["result"])
phase_duration_seconds = Histogram("kloros_phase_duration_seconds", "PHASE run duration in seconds",
                                   buckets=[60, 300, 600, 1800, 3600, 7200, 14400])

# D-REAM metrics
dream_runs_total = Counter("kloros_dream_runs_total", "Total D-REAM runs", ["result"])
dream_duration_seconds = Histogram("kloros_dream_duration_seconds", "D-REAM run duration in seconds",
                                   buckets=[10, 30, 60, 300, 600, 1800, 3600])

# Symptom tracking
symptoms_total = Counter("kloros_symptoms_total", "Observer-reported symptoms (24h rolling handled externally)", ["kind"])

# Escalation flags
escalation_flag_gauge = Gauge("kloros_escalation_flag", "1 if escalation flag is set for kind", ["kind"])

# GPU canary budget and cooldown
budget_seconds_remaining = Gauge("kloros_gpu_budget_seconds_remaining", "Remaining GPU canary downtime budget in seconds")
canary_cooldown_seconds = Gauge("kloros_gpu_canary_cooldown_seconds", "Seconds until canary eligible again")

# Canary operations
canary_runs_total = Counter("kloros_canary_runs_total", "Total canary runs", ["result", "mode"])
canary_duration_seconds = Gauge("kloros_canary_duration_seconds", "Last canary duration in seconds")
canary_restore_fail_total = Counter("kloros_canary_restore_fail_total", "Failed production restores")

# SPICA resource metrics (Nov 5, 2025 - ResourceGovernor observability)
spica_instances_current = Gauge("kloros_spica_instances_current", "Current number of SPICA instances")
spica_disk_free_gb = Gauge("kloros_spica_disk_free_gb", "Free disk space in GB")
spica_circuit_breaker_state = Gauge("kloros_spica_circuit_breaker_state", "Circuit breaker state (0=closed, 1=open, 2=half_open)")

spica_spawn_attempts_total = Counter("kloros_spica_spawn_attempts_total", "Total SPICA spawn attempts", ["result"])
spica_spawn_blocks_total = Counter("kloros_spica_spawn_blocks_total", "SPICA spawns blocked by ResourceGovernor", ["reason"])
spica_circuit_breaker_transitions = Counter("kloros_spica_circuit_breaker_transitions", "Circuit breaker state transitions", ["from_state", "to_state"])

spica_spawn_duration_seconds = Histogram("kloros_spica_spawn_duration_seconds", "SPICA instance spawn duration in seconds",
                                         buckets=[1, 5, 10, 30, 60, 120, 300, 600])
spica_instance_lifetime_seconds = Histogram("kloros_spica_instance_lifetime_seconds", "SPICA instance lifetime in seconds",
                                           buckets=[60, 300, 600, 1800, 3600, 7200, 14400, 86400])
