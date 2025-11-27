# RedundantExecutor - Robust Task Execution for KLoROS

## Overview

`RedundantExecutor` provides production-ready retry and fallback execution for KLoROS orchestration. It implements a resilient execution pattern that:

1. **Retries** the primary executor with exponential backoff
2. **Falls back** to alternative executors when primary exhausts retries
3. **Emits metrics** for observability and monitoring
4. **Supports both sync and async** execution patterns

## Architecture

```
RedundantExecutor
├── primary_executor: Callable         # Main execution path
├── fallback_chain: List[Callable]     # Backup executors
├── retry_config: RetryConfig
│   ├── max_retries: int = 2           # Retry attempts per executor
│   ├── backoff_ms: int = 100          # Initial backoff delay
│   └── timeout_ms: int = 30000        # Per-executor timeout
└── execute_with_redundancy(task) → Result
```

## Execution Flow

```
┌─────────────────────────────────────────────────────────┐
│ Task Submitted                                          │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│ Try Primary Executor                                    │
│ • Attempt 1: immediate                                  │
│ • Attempt 2: after 100ms backoff                        │
│ • Attempt 3: after 200ms backoff                        │
│ • Attempt N: after 2^(N-2) * backoff_ms                 │
└─────────────────────────────────────────────────────────┘
                          │
                ┌─────────┴─────────┐
                │ Success?          │
                └─────────┬─────────┘
                          │
            ┌─────────────┴─────────────┐
            │ YES                   NO  │
            ▼                           ▼
    ┌───────────────┐      ┌────────────────────────┐
    │ Return Result │      │ Try Fallback 1         │
    │ Metric: ✓     │      └────────────────────────┘
    └───────────────┘                  │
                             ┌─────────┴─────────┐
                             │ Success?          │
                             └─────────┬─────────┘
                                       │
                         ┌─────────────┴─────────────┐
                         │ YES                   NO  │
                         ▼                           ▼
                 ┌───────────────┐      ┌────────────────────────┐
                 │ Return Result │      │ Try Fallback 2...N     │
                 │ Metric: ⚠      │      └────────────────────────┘
                 └───────────────┘                  │
                                          ┌─────────┴─────────┐
                                          │ All Failed?       │
                                          └─────────┬─────────┘
                                                    │
                                                    ▼
                                    ┌────────────────────────────┐
                                    │ ExecutionExhaustedError    │
                                    │ Metric: ✗                  │
                                    └────────────────────────────┘
```

## Usage

### Basic Usage

```python
from kloros.orchestration.redundant_executor import (
    RedundantExecutor,
    RetryConfig,
)

def process_task(task):
    return f"processed_{task}"

executor = RedundantExecutor(primary=process_task)
result = executor.execute("my_task")
```

### With Retry Configuration

```python
config = RetryConfig(
    max_retries=3,          # 4 total attempts (initial + 3 retries)
    backoff_ms=200,         # Start with 200ms backoff
    timeout_ms=30000        # 30 second timeout per attempt
)

executor = RedundantExecutor(
    primary=unreliable_processor,
    config=config
)

result = executor.execute(task)
```

### With Fallback Chain

```python
def primary_executor(task):
    # Primary logic (e.g., SPICA processing)
    return spica_process(task)

def fallback_baseline(task):
    # Fallback to baseline model
    return baseline_process(task)

def fallback_emergency(task):
    # Emergency fallback (always succeeds)
    return {'status': 'emergency', 'data': task}

executor = RedundantExecutor(
    primary=primary_executor,
    fallbacks=[fallback_baseline, fallback_emergency],
    config=RetryConfig(max_retries=2, backoff_ms=100)
)

result = executor.execute(observation)
```

### Async Execution

```python
async def async_processor(task):
    await asyncio.sleep(0.1)
    return process(task)

async def async_fallback(task):
    await asyncio.sleep(0.05)
    return fallback_process(task)

executor = RedundantExecutor(
    primary=async_processor,
    fallbacks=[async_fallback]
)

result = await executor.async_execute(task)
```

### Error Handling

```python
from kloros.orchestration.redundant_executor import ExecutionExhaustedError

try:
    result = executor.execute(task)
except ExecutionExhaustedError as e:
    # All executors failed
    logger.error(f"Execution exhausted: {len(e.errors)} total failures")

    # Access individual errors
    for idx, error in enumerate(e.errors, 1):
        logger.error(f"  Attempt {idx}: {type(error).__name__}: {error}")

    # Trigger escalation, alerts, etc.
    raise
```

## Configuration Options

### RetryConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_retries` | int | 2 | Number of retry attempts (0 = one attempt only) |
| `backoff_ms` | int | 100 | Initial backoff delay in milliseconds |
| `timeout_ms` | int | 30000 | Timeout per execution attempt in milliseconds |

### Backoff Strategy

Exponential backoff is used:
- Attempt 1: immediate
- Attempt 2: `backoff_ms * 2^0 = backoff_ms`
- Attempt 3: `backoff_ms * 2^1 = 2 * backoff_ms`
- Attempt N: `backoff_ms * 2^(N-2)`

Example with `backoff_ms=100`:
- Attempt 1: 0ms
- Attempt 2: 100ms delay
- Attempt 3: 200ms delay
- Attempt 4: 400ms delay

## Metrics

The executor emits metrics for observability:

| Metric | Type | Description |
|--------|------|-------------|
| `redundant_execution_primary_success` | Event | Primary executor succeeded |
| `redundant_execution_fallback_used` | Event | Fallback executor succeeded |
| `redundant_execution_total_failure` | Event | All executors failed |

Metrics are currently logged as structured events:
```
METRIC: redundant_execution_primary_success timestamp=2025-11-24T21:53:59.826754+00:00
```

These can be integrated with Prometheus/Grafana by:
1. Adding prometheus_client counters in `metrics.py`
2. Updating `_log_metric()` to increment actual metrics
3. Exposing metrics endpoint

## Integration Patterns

### KLoROS Orchestration

```python
from kloros.orchestration.redundant_executor import RedundantExecutor, RetryConfig

class OrchestrationLayer:
    def __init__(self):
        self.executor = RedundantExecutor(
            primary=self._spica_process,
            fallbacks=[
                self._baseline_process,
                self._emergency_process
            ],
            config=RetryConfig(
                max_retries=2,
                backoff_ms=100,
                timeout_ms=30000
            )
        )

    def process_observation(self, observation):
        return self.executor.execute(observation)

    def _spica_process(self, obs):
        # SPICA instance processing
        pass

    def _baseline_process(self, obs):
        # Baseline fallback
        pass

    def _emergency_process(self, obs):
        # Emergency fallback (always succeeds)
        pass
```

### Autonomous Loops

```python
class AutonomousLoop:
    def __init__(self):
        self.phase_executor = RedundantExecutor(
            primary=self._run_phase,
            config=RetryConfig(max_retries=1, timeout_ms=7200000)  # 2 hour timeout
        )

    def run_cycle(self):
        try:
            phase_result = self.phase_executor.execute({'mode': 'predictive'})
            return self._analyze_and_act(phase_result)
        except ExecutionExhaustedError as e:
            self._escalate_to_human(e)
            raise
```

### Canary Operations

```python
class CanaryRunner:
    def __init__(self):
        self.executor = RedundantExecutor(
            primary=self._run_canary,
            fallbacks=[self._restore_production],
            config=RetryConfig(
                max_retries=0,      # No retries for canary
                timeout_ms=60000    # 60s budget
            )
        )

    def execute_canary(self, config):
        try:
            return self.executor.execute(config)
        except ExecutionExhaustedError:
            # Fallback already restored production
            return {'status': 'canary_failed_production_restored'}
```

## Best Practices

1. **Set appropriate timeouts**: Match timeout to expected execution time + buffer
2. **Limit retries**: More retries = longer latency. Use 1-3 retries for most cases
3. **Order fallbacks by preference**: List fallbacks from most to least preferred
4. **Handle ExecutionExhaustedError**: Always have a plan for total failure
5. **Monitor metrics**: Track success rates and fallback usage
6. **Use async for I/O**: Prefer `async_execute()` for I/O-bound tasks
7. **Keep executors pure**: Executors should be stateless functions
8. **Log failures**: Executor logs all attempts; review logs for patterns

## Advanced Usage

### Conditional Fallbacks

```python
def smart_executor(task):
    if task.get('priority') == 'high':
        return expensive_process(task)
    return standard_process(task)

def fallback_degraded(task):
    # Degraded mode for any priority
    return minimal_process(task)

executor = RedundantExecutor(
    primary=smart_executor,
    fallbacks=[fallback_degraded]
)
```

### Per-Task Configuration

```python
def execute_with_config(task, config):
    executor = RedundantExecutor(
        primary=lambda t: process(t),
        config=config
    )
    return executor.execute(task)

# High-priority: aggressive retries
critical_result = execute_with_config(
    critical_task,
    RetryConfig(max_retries=5, backoff_ms=50)
)

# Low-priority: conservative retries
batch_result = execute_with_config(
    batch_task,
    RetryConfig(max_retries=1, backoff_ms=500)
)
```

### Circuit Breaker Integration

```python
class CircuitBreakerExecutor:
    def __init__(self, circuit_breaker):
        self.cb = circuit_breaker
        self.executor = RedundantExecutor(
            primary=self._guarded_execute,
            fallbacks=[self._fallback]
        )

    def _guarded_execute(self, task):
        if self.cb.is_open():
            raise RuntimeError("Circuit breaker open")

        try:
            result = expensive_operation(task)
            self.cb.record_success()
            return result
        except Exception as e:
            self.cb.record_failure()
            raise

    def _fallback(self, task):
        return cached_or_degraded_result(task)

    def execute(self, task):
        return self.executor.execute(task)
```

## Testing

Run the test suite:

```bash
PYTHONPATH=/home/kloros/src pytest src/kloros/orchestration/tests/test_redundant_executor.py -v
```

Run usage examples:

```bash
PYTHONPATH=/home/kloros/src python3 src/kloros/orchestration/examples/redundant_executor_usage.py
```

## Implementation Notes

- **Thread-safe**: Synchronous executor is thread-safe for stateless executors
- **Timeout enforcement**: Uses `signal.SIGALRM` (sync) and `asyncio.wait_for` (async)
- **Error collection**: All errors are collected in `_errors` list
- **Logging**: Comprehensive logging at INFO, WARNING, and ERROR levels
- **No external dependencies**: Uses only Python standard library

## Performance Characteristics

- **Overhead**: <1ms for successful primary execution
- **Backoff delay**: Configurable, starts at `backoff_ms`
- **Memory**: O(N) where N = number of errors collected
- **CPU**: Minimal, mostly I/O waiting during backoff

## Future Enhancements

Potential improvements (not yet implemented):

- [ ] Prometheus metrics integration
- [ ] Jitter in exponential backoff
- [ ] Circuit breaker pattern
- [ ] Rate limiting
- [ ] Executor health tracking
- [ ] Dynamic fallback selection based on error type
- [ ] Telemetry and distributed tracing
- [ ] Configurable retry policies (linear, exponential, fibonacci)

## See Also

- `/home/kloros/src/kloros/orchestration/autonomous_loop.py` - Autonomous self-healing loop
- `/home/kloros/src/kloros/orchestration/metrics.py` - KLoROS metrics
- `/home/kloros/src/kloros/orchestration/escalation_manager.py` - Escalation handling
