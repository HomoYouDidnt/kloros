# KLoROS Autonomous Memory Decay Guide

## Overview

KLoROS now manages her own memory decay automatically! A background thread runs decay updates every hour (configurable) without blocking voice interactions.

## How It Works

When KLoROS starts up, she automatically:

1. **Initializes** the decay manager in a background thread
2. **Runs decay updates** every 60 minutes (default)
3. **Updates decay scores** for all memories based on age
4. **Deletes old memories** that fall below threshold (0.1)
5. **Logs statistics** about what was cleaned up

All of this happens **autonomously** while KLoROS continues normal voice interactions.

## Configuration

All settings are in `/home/kloros/.kloros_env`:

### Enable/Disable Features

```bash
# Turn autonomous decay on/off
KLR_AUTO_START_DECAY=1           # 1=enabled, 0=disabled

# Individual memory features
KLR_ENABLE_EMBEDDINGS=1          # Semantic search
KLR_ENABLE_GRAPH=1               # Graph relationships
KLR_ENABLE_SENTIMENT=1           # Emotional tracking
KLR_ENABLE_DECAY=1               # Memory decay
```

### Decay Timing

```bash
# How often to run decay updates (minutes)
KLR_DECAY_UPDATE_INTERVAL=60     # Default: every hour

# Memory half-lives (hours until score reaches 0.5)
KLR_DECAY_EPISODIC_HALF_LIFE=168      # 7 days - specific events
KLR_DECAY_SEMANTIC_HALF_LIFE=720      # 30 days - knowledge/summaries
KLR_DECAY_PROCEDURAL_HALF_LIFE=2160   # 90 days - learned skills
KLR_DECAY_EMOTIONAL_HALF_LIFE=360     # 15 days - emotional memories
KLR_DECAY_REFLECTIVE_HALF_LIFE=1440   # 60 days - insights
```

### Decay Behavior

```bash
# How decay works
KLR_DECAY_IMPORTANCE_RESISTANCE=0.7   # Important memories resist decay
KLR_DECAY_ACCESS_REFRESH=0.5          # Accessing refreshes memory
KLR_DECAY_DELETION_THRESHOLD=0.1      # Delete below this score
KLR_DECAY_RECENT_ACCESS_WINDOW=24     # Hours for "recent" boost
```

## What Happens During Decay Updates

Every hour (by default), KLoROS will:

1. **Calculate decay scores** for all memories:
   - Recent memories: High score (1.0)
   - Old memories: Lower score (0.0-1.0)
   - Important memories: Decay slower
   - Accessed memories: Get refreshed

2. **Delete heavily decayed memories**:
   - Memories below 0.1 threshold are deleted
   - Frees up database space
   - Improves query performance

3. **Log statistics**:
   ```
   [autonomous_decay] Iteration #5 complete in 2.3s: 2306 updated, 7694 deleted
   [autonomous_decay] Stats: 9942 events, avg decay: 0.968, near deletion: 156
   ```

## Example Log Output

When KLoROS starts:
```
[memory] ✅ Started autonomous decay manager (updates every 60 minutes)
```

During operation:
```
[autonomous_decay] Starting decay update iteration #1
[autonomous_decay] Iteration #1 complete in 2.5s: 10243 updated, 0 deleted
[autonomous_decay] Stats: 10243 events, avg decay: 0.992, near deletion: 12
```

When KLoROS shuts down:
```
[memory] ✅ Stopped autonomous decay manager
```

## Monitoring

To check if decay manager is running:

```python
from kloros_memory.autonomous_decay import get_autonomous_decay_manager

manager = get_autonomous_decay_manager()
if manager and manager.is_running():
    print("Decay manager is running")
else:
    print("Decay manager is NOT running")
```

To get decay statistics manually:

```python
from kloros_memory.decay import DecayEngine

engine = DecayEngine()
stats = engine.get_decay_statistics()

print(f"Total events: {stats['overall']['total_events']}")
print(f"Average decay: {stats['overall']['avg_decay']:.3f}")
print(f"Near deletion: {stats['near_deletion']}")
```

## Customization Examples

### More Aggressive Decay (Forget Faster)

```bash
# Shorter half-lives
KLR_DECAY_EPISODIC_HALF_LIFE=24    # 1 day instead of 7
KLR_DECAY_SEMANTIC_HALF_LIFE=168   # 7 days instead of 30

# Higher deletion threshold
KLR_DECAY_DELETION_THRESHOLD=0.3   # Delete at 0.3 instead of 0.1

# More frequent updates
KLR_DECAY_UPDATE_INTERVAL=30       # Every 30 minutes
```

### More Conservative Decay (Keep Longer)

```bash
# Longer half-lives
KLR_DECAY_EPISODIC_HALF_LIFE=336   # 14 days instead of 7
KLR_DECAY_SEMANTIC_HALF_LIFE=2160  # 90 days instead of 30

# Lower deletion threshold
KLR_DECAY_DELETION_THRESHOLD=0.05  # Delete only at 0.05

# Less frequent updates
KLR_DECAY_UPDATE_INTERVAL=180      # Every 3 hours

# Stronger importance resistance
KLR_DECAY_IMPORTANCE_RESISTANCE=0.9  # Important memories barely decay
```

### Disable Autonomous Decay

If you want to manage decay manually:

```bash
# In .kloros_env
KLR_AUTO_START_DECAY=0

# Then run manually when needed:
python3 src/kloros_memory/decay_daemon.py --once
```

## Performance Impact

The decay manager runs in a **background thread** and has minimal impact:

- **CPU**: <1% during updates (runs every 60 min)
- **Memory**: ~5 MB for the thread
- **I/O**: Brief disk access during database updates
- **Voice Interaction**: **ZERO impact** - runs independently

Updates take 2-5 seconds for 10k events, happening in the background without blocking.

## Troubleshooting

### Issue: Decay not running

**Check:**
```bash
# In .kloros_env
KLR_AUTO_START_DECAY=1  # Must be 1
KLR_ENABLE_MEMORY=1     # Must be 1
```

**Look for log message:**
```
[memory] ✅ Started autonomous decay manager
```

If not present, check for errors:
```
[memory] ⚠️ Failed to start autonomous decay manager: [error]
```

### Issue: Too many memories being deleted

**Adjust thresholds:**
```bash
# Lower threshold = keep more
KLR_DECAY_DELETION_THRESHOLD=0.05  # Instead of 0.1

# Longer half-lives = slower decay
KLR_DECAY_EPISODIC_HALF_LIFE=336   # 14 days instead of 7
```

### Issue: Memories not decaying enough

**Increase decay rate:**
```bash
# Shorter half-lives = faster decay
KLR_DECAY_EPISODIC_HALF_LIFE=84    # 3.5 days instead of 7

# Higher threshold = delete sooner
KLR_DECAY_DELETION_THRESHOLD=0.2   # Instead of 0.1

# More frequent updates
KLR_DECAY_UPDATE_INTERVAL=30       # Every 30 minutes
```

## Manual Control

If you need to control decay manually:

```python
from kloros_memory.autonomous_decay import (
    start_autonomous_decay,
    stop_autonomous_decay,
    get_autonomous_decay_manager
)

# Stop current manager
stop_autonomous_decay()

# Start with custom settings
manager = start_autonomous_decay(update_interval_minutes=30)

# Check status
if manager.is_running():
    print("Running!")
```

## Summary

KLoROS now manages her own memory automatically:

- ✅ **Autonomous**: Runs in background thread
- ✅ **Configurable**: Tune via environment variables
- ✅ **Non-blocking**: Doesn't affect voice interactions
- ✅ **Efficient**: Updates thousands of events in seconds
- ✅ **Smart**: Important and recently accessed memories persist longer

**Default behavior:** Every hour, update decay scores and clean up old memories. Works great out of the box!

---

**Last Updated:** November 1, 2025
