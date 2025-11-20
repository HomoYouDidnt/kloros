"""
Genome mutation operators for D-REAM zooid evolution.

Provides parameter mutation for creating zooid variants.
"""
import random


def mutate_params(niche: str) -> dict:
    """
    Generate phenotype parameters for a zooid variant.

    Args:
        niche: Niche name (e.g., "latency_monitoring", "flow_regulation")

    Returns:
        Dictionary of phenotype parameters for template rendering
    """
    # Base parameters common to all niches
    params = {
        "poll_interval_sec": round(random.uniform(0.5, 5.0), 2),
        "batch_size": random.choice([10, 20, 50, 100]),
        "timeout_sec": random.choice([5, 10, 30, 60]),
        "log_level": random.choice(["INFO", "DEBUG", "WARNING"]),
    }

    # Niche-specific mutations
    if niche == "latency_monitoring":
        params.update({
            "p95_threshold_ms": random.choice([100, 200, 500, 1000]),
            "window_size": random.choice([20, 50, 100]),
            "alert_percentile": random.choice([90, 95, 99]),
        })
    elif niche == "flow_regulation":
        params.update({
            "max_queue_depth": random.choice([100, 500, 1000, 5000]),
            "backpressure_threshold": round(random.uniform(0.7, 0.95), 2),
            "drain_rate_multiplier": round(random.uniform(1.0, 3.0), 2),
        })
    elif niche == "housekeeping":
        params.update({
            "retention_days": random.choice([14, 30, 60, 90]),
            "vacuum_interval_days": random.choice([3, 7, 14]),
            "cleanup_batch_size": random.choice([100, 500, 1000, 5000]),
            "max_log_size_mb": random.choice([10, 50, 100, 200]),
        })
    elif niche == "predictive_modeling":
        params.update({
            "history_window_sec": random.choice([300, 600, 1800]),
            "prediction_horizon_sec": random.choice([60, 300, 600]),
            "model_type": random.choice(["linear", "ewma", "arima"]),
        })
    elif niche == "backpressure_control":
        params.update({
            "pressure_threshold": round(random.uniform(0.6, 0.9), 2),
            "recovery_rate": round(random.uniform(0.1, 0.5), 2),
            "circuit_breaker_timeout_sec": random.choice([30, 60, 120]),
        })
    elif niche == "maintenance_housekeeping":
        params.update({
            "maintenance_interval_hours": round(random.uniform(12.0, 48.0), 1),
            "daily_maintenance_hour": random.choice([1, 2, 3, 4, 5]),
            "memory_cleanup_enabled": random.choice([True, False]),
            "python_cache_cleanup_enabled": random.choice([True, False]),
        })
    elif niche == "memory_decay":
        params.update({
            "update_interval_minutes": random.choice([30, 60, 90, 120]),
            "deletion_threshold": round(random.uniform(0.8, 0.95), 2),
            "decay_half_life_hours": random.choice([24, 48, 72]),
        })
    elif niche == "promotion_validation":
        params.update({
            "scan_interval_sec": random.choice([30, 60, 120]),
            "max_fitness_threshold": round(random.uniform(0.7, 0.95), 2),
            "min_fitness_threshold": round(random.uniform(0.3, 0.6), 2),
            "validation_retries": random.choice([1, 2, 3]),
        })
    elif niche == "observability_logging":
        params.update({
            "flush_interval_sec": round(random.uniform(0.5, 5.0), 2),
            "buffer_size": random.choice([100, 500, 1000]),
            "log_rotation_mb": random.choice([10, 50, 100]),
            "compression_enabled": random.choice([True, False]),
        })

    return params
