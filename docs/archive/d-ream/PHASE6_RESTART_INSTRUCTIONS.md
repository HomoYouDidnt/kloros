# Phase 6 Watcher Restart Instructions

## Current Status
There are old watcher processes (PIDs 395454, 699476) running with outdated code.
All Phase 6 Quick Hardening features have been implemented and are ready for use.

## To Restart Watchers (as kloros user):

```bash
# 1. Kill old processes
pkill -9 -f repairlab_queue_watcher.py

# 2. Verify they're gone
pgrep -af repairlab_queue_watcher.py || echo "All cleared"

# 3. Restart via systemd (if configured)
systemctl --user daemon-reload
systemctl --user restart repairlab-queue-watcher.service
systemctl --user status repairlab-queue-watcher.service

# OR manually restart:
cd /home/kloros
nohup /home/kloros/.venv/bin/python3 /home/kloros/bin/repairlab_queue_watcher.py >> /home/kloros/logs/repairlab_watcher/stdout.log 2>&1 &
```

## Validation Commands:

```bash
# Check telemetry in newest challenger
ls -1 /tmp/toolgen_challengers/challenger_*.json | tail -1 | xargs cat | jq '{
  repair_strategy, repair_pattern_id, repair_attempts, repair_details, bundle_sha256, lineage
}'

# Verify timers
systemctl --user list-timers | grep -E 'library-extract|auto-specder'
sudo systemctl list-timers | grep toolgen-challenger-cleanup

# Monitor watcher logs
journalctl --user -u repairlab-queue-watcher.service -f
# OR
tail -f /home/kloros/logs/repairlab_watcher/runs.log
```

## Files Modified:
- `/home/kloros/bin/repairlab_queue_watcher.py` - Backoff + failure tracking
- `/home/kloros/bin/toolgen_challenger_cleanup.sh` - TTL pruning script
- `/etc/systemd/system/toolgen-challenger-cleanup.{service,timer}` - Weekly cleanup
- `/home/kloros/src/phase/domains/spica_toolgen.py` - Meta-repair tag

## Quick Hardening Features Implemented:
✅ Backoff & Quarantine (3 failures → `processed/hard_fail/`)
✅ TTL Pruning (weekly cleanup, 7-day retention)
✅ Meta-repair tag (`meta_repair: true/false` in metrics)
✅ End-to-end telemetry flow validated
