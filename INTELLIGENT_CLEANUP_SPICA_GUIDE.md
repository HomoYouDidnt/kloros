# Enhanced SPICA: Intelligent Cleanup Optimization

## Overview

The SPICA has been enhanced to optimize intelligent cleanup parameters, enabling D-REAM to automatically discover optimal configurations for file importance scoring and deletion confidence.

## New Optimizable Parameters

### 1. Deletion Confidence Threshold (0.70 - 0.95)
**What it controls**: Minimum confidence required to delete a file
- **Lower values** (0.70-0.80): More aggressive, deletes more files
- **Higher values** (0.85-0.95): More conservative, only deletes obvious obsolete files
- **Current default**: 0.85

### 2. Signal Weights (must sum to 1.0)

#### Git Weight (0.20 - 0.60)
Importance of git tracking status and commit history
- High weight: Prioritizes files in version control
- Low weight: Less emphasis on git status

#### Dependency Weight (0.15 - 0.45)
Importance of being imported by other code
- High weight: Strong protection for library/utility files
- Low weight: Less emphasis on import relationships

#### Usage Weight (0.10 - 0.35)
Importance of recent access/modification
- High weight: Recently touched files more protected
- Low weight: Age matters less

#### Systemd Weight (0.05 - 0.20)
Importance of being referenced in system services
- High weight: Strong protection for service-critical files
- Low weight: Less emphasis on systemd references

### 3. Importance Thresholds

Thresholds that determine classification boundaries:

- **CRITICAL threshold** (0.75-0.90): Score above this = CRITICAL (never delete)
- **IMPORTANT threshold** (0.55-0.75): Score above this = IMPORTANT (never delete)
- **NORMAL threshold** (0.25-0.45): Score above this = NORMAL (never delete)
- **LOW threshold** (0.10-0.25): Score above this = LOW (usually protected)
- Below LOW threshold = OBSOLETE (candidate for deletion)

## How D-REAM Optimizes

### Fitness Function Components

```python
fitness = (
    performance_score * 0.20 +           # Cleanup speed
    disk_efficiency_score * 0.20 +       # Space freed
    health_score * 0.20 +                # System health
    retention_balance_score * 0.15 +     # Data retention
    cleanup_accuracy_score * 0.25        # NEW: Classification accuracy
)
```

### Cleanup Accuracy Scoring

The most important new metric is **classification_accuracy**:

```
classification_accuracy = files_correctly_identified / total_files_analyzed
```

Where:
- **True Positives**: Obsolete files correctly identified for deletion
- **True Negatives**: Important files correctly protected
- **False Positives**: Important files incorrectly marked for deletion (BAD!)
- **False Negatives**: Obsolete files not deleted (less bad, conservative)

### Evolutionary Process

1. **Initial Population**: Generate candidates with random parameter combinations
2. **Evaluation**: Test each configuration:
   - Run intelligent cleanup with those parameters
   - Measure classification accuracy
   - Check for false positives (deleted important files)
   - Calculate overall fitness
3. **Selection**: R-Zero tournament selects high-fitness configurations
4. **Mutation**: Create variations of winners
5. **Iteration**: Repeat until optimal parameters found

## Example Scenarios

### Scenario A: Conservative System (Production Database Server)
**Optimal Parameters**:
```python
deletion_confidence_threshold = 0.92  # Very conservative
git_weight = 0.50  # High - tracked files very important
dependency_weight = 0.30  # High - imported code protected
usage_weight = 0.15  # Moderate
systemd_weight = 0.05  # Low - few system services

critical_threshold = 0.85  # Easy to be classified as CRITICAL
important_threshold = 0.65
normal_threshold = 0.35
low_threshold = 0.15
```

**Result**: Very safe, rarely deletes anything questionable, low false positive rate

### Scenario B: Aggressive Development Workspace
**Optimal Parameters**:
```python
deletion_confidence_threshold = 0.75  # More aggressive
git_weight = 0.25  # Lower - not all files tracked
dependency_weight = 0.20  # Lower
usage_weight = 0.40  # High - recent activity matters most
systemd_weight = 0.15  # Higher - service files protected

critical_threshold = 0.80  # Harder to be CRITICAL
important_threshold = 0.60
normal_threshold = 0.30
low_threshold = 0.12
```

**Result**: More aggressive cleanup, frees more space, still safe due to usage-based protection

### Scenario C: Balanced General Purpose
**Optimal Parameters** (what D-REAM might discover):
```python
deletion_confidence_threshold = 0.87
git_weight = 0.38
dependency_weight = 0.28
usage_weight = 0.22
systemd_weight = 0.12

critical_threshold = 0.82
important_threshold = 0.63
normal_threshold = 0.34
low_threshold = 0.16
```

**Result**: Good balance between safety and effectiveness

## Metrics to Track

D-REAM will optimize based on these metrics:

1. **Classification Accuracy** (primary):
   - Target: > 98% accuracy
   - Measures how well parameters identify importance correctly

2. **False Positive Rate** (critical):
   - Target: < 0.1% (less than 1 in 1000 important files deleted)
   - Heavy penalty in fitness function

3. **True Positive Rate** (secondary):
   - Target: > 95% (catches most obsolete files)
   - Rewards for identifying genuine cleanup candidates

4. **Disk Space Freed** (efficiency):
   - More space freed = higher fitness (if accuracy maintained)

5. **Safety Margin** (robustness):
   - Higher deletion confidence threshold = safer
   - Balanced against effectiveness

## Running Optimization

### Method 1: Via D-REAM Runner
```bash
# Create experiment config
cat > /tmp/housekeeping_cleanup_experiment.yaml << 'YAML'
experiment:
  name: "housekeeping_intelligent_cleanup_v1"
  domain: "spica_housekeeping"
  epochs: 20
  population_size: 8
  mutation_rate: 0.15
YAML

# Run optimization
/home/kloros/.venv/bin/python3 -m src.dream.runner \
  --config /tmp/housekeeping_cleanup_experiment.yaml \
  --logdir /home/kloros/logs/dream/housekeeping_cleanup \
  --epochs-per-cycle 5
```

### Method 2: Direct SPICA Test
```python
from src.phase.domains.spica_housekeeping import SpicaHousekeeping

# Create evaluator
evaluator = SpicaHousekeeping()

# Test a specific configuration
candidate = {
    "retention_days": 30,
    "vacuum_days": 7,
    "reflection_retention_days": 60,
    "reflection_log_max_mb": 50,
    "max_uncondensed_episodes": 100,
    "backup_retention_days": 30,
    "max_backups_per_file": 3,
    
    # New intelligent cleanup parameters
    "deletion_confidence_threshold": 0.87,
    "git_signal_weight": 0.38,
    "dependency_signal_weight": 0.28,
    "usage_signal_weight": 0.22,
    "systemd_signal_weight": 0.12,
    "critical_importance_threshold": 0.82,
    "important_importance_threshold": 0.63,
    "normal_importance_threshold": 0.34,
    "low_importance_threshold": 0.16
}

# Evaluate
result = evaluator.evaluate(candidate)
print(f"Classification Accuracy: {result['classification_accuracy']:.2%}")
print(f"Fitness: {result['fitness']:.3f}")
```

## Expected Outcomes

After D-REAM optimization:

### Before Optimization (Manual Parameters)
- Classification accuracy: ~92%
- False positive rate: ~2%
- Deletion confidence: Fixed at 0.85
- Signal weights: Manually tuned

### After Optimization (D-REAM Tuned)
- Classification accuracy: **~97-99%**
- False positive rate: **< 0.5%**
- Deletion confidence: **Adaptive** (optimized for your environment)
- Signal weights: **Environment-specific** (e.g., high git weight if most files tracked)

### Adaptive Learning

The SPICA will discover:
1. **Your environment characteristics**:
   - If you use git heavily → higher git weight
   - If you have complex dependencies → higher dependency weight
   - If you frequently access files → higher usage weight

2. **Optimal safety thresholds**:
   - Conservative for production-critical directories
   - More aggressive for temporary/cache directories

3. **Classification boundaries**:
   - Where to draw the line between IMPORTANT and NORMAL
   - How strict to be with OBSOLETE classification

## Safety Mechanisms

### Built-in Protections
1. **Hard limits** on deletion confidence (0.70-0.95 range)
2. **Weight normalization** (must sum to 1.0)
3. **Threshold ordering** (CRITICAL > IMPORTANT > NORMAL > LOW)
4. **False positive penalties** in fitness function
5. **Dry-run mode** by default until manually enabled

### Validation
- Each configuration tested in dry-run mode first
- Classification accuracy measured on known-good/known-bad files
- Heavy penalty for any false positives
- Configurations that delete important files get fitness = 0.0

## Integration with Existing Housekeeping

The enhanced SPICA optimizes **both**:
1. Traditional housekeeping parameters (retention, vacuum, backups)
2. Intelligent cleanup parameters (weights, thresholds, confidence)

This creates a holistic optimization where:
- Traditional cleanup handles structured data (events, logs, DBs)
- Intelligent cleanup handles unstructured files (backups, temp files)
- Both work together for optimal system health

## Conclusion

By making the intelligent cleanup parameters tunable through SPICA, D-REAM can:
- **Automatically discover** optimal settings for your environment
- **Adapt** to your usage patterns
- **Balance** safety vs. effectiveness
- **Learn** from outcomes to improve classification
- **Maintain** high accuracy while freeing disk space

The result is a self-optimizing housekeeping system that gets smarter over time!
