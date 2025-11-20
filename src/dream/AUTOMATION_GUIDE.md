# D-REAM Automation Guide

## Overview

This guide explains how to enable automatic D-REAM evaluation after each PHASE window.

## Status

**Current:** Manual trigger mode ✅ (safe)
**Available:** Automatic timer mode 🟡 (disabled by default)

## Manual Trigger (Current)

```bash
# Set environment
export DREAM_ARTIFACTS=/home/kloros/src/dream/artifacts
export PYTHONPATH=/home/kloros:$PYTHONPATH

# Trigger D-REAM for a specific episode
python3 -c "from src.phase.hooks import on_phase_window_complete; on_phase_window_complete('<episode_id>')"

# Or use the automation script
/home/kloros/.venv/bin/python3 /home/kloros/src/dream/auto_dream_eval.py <episode_id>
```

## Automatic Timer Mode (How to Enable)

### Option 1: Systemd Timer (Recommended)

Create a new systemd service that runs after PHASE completes:

```bash
# Create service
sudo tee /etc/systemd/system/dream-auto-eval.service << 'EOF'
[Unit]
Description=D-REAM Automatic Evaluation
After=network.target

[Service]
Type=oneshot
User=kloros
Group=kloros
WorkingDirectory=/home/kloros
Environment="DREAM_ARTIFACTS=/home/kloros/src/dream/artifacts"
Environment="PYTHONPATH=/home/kloros"
ExecStart=/home/kloros/.venv/bin/python3 /home/kloros/src/dream/auto_dream_eval.py
StandardOutput=append:/home/kloros/logs/dream_auto_eval.log
StandardError=append:/home/kloros/logs/dream_auto_eval.log

[Install]
WantedBy=multi-user.target
EOF

# Create timer (runs every hour)
sudo tee /etc/systemd/system/dream-auto-eval.timer << 'EOF'
[Unit]
Description=D-REAM Auto Evaluation Timer
Requires=dream-auto-eval.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Unit=dream-auto-eval.service

[Install]
WantedBy=timers.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable dream-auto-eval.timer
sudo systemctl start dream-auto-eval.timer

# Check status
sudo systemctl status dream-auto-eval.timer
```

### Option 2: PHASE Integration Hook

Add to PHASE test runner completion:

```python
# In PHASE test runner after window completes
from src.dream.auto_dream_eval import main as dream_eval

try:
    dream_eval()  # Auto-evaluates latest window
except Exception as e:
    logger.warning(f"D-REAM auto-eval failed: {e}")
```

### Option 3: Cron Job

```bash
# Add to kloros crontab
sudo -u kloros crontab -e

# Run every hour
0 * * * * /home/kloros/.venv/bin/python3 /home/kloros/src/dream/auto_dream_eval.py >> /home/kloros/logs/dream_auto_eval.log 2>&1
```

## Guards

The automation script includes safety guards:

1. **Empty Check**: Skips if phase_raw/<episode>.jsonl missing or empty
2. **Lineage Tracking**: Every evaluation logs origin, episode_id, SHAs
3. **Error Handling**: Failures logged but don't crash timer
4. **Admission Gates**: Only candidates passing thresholds are admitted

## Monitoring

### Check Logs

```bash
# Auto-eval logs
tail -f /home/kloros/logs/dream_auto_eval.log

# D-REAM evaluations
ls -lt /home/kloros/src/dream/artifacts/candidates/

# Adoptions
cat /home/kloros/src/dream/artifacts/adoptions.jsonl | jq
```

### Dashboard

Visit http://localhost:5000/api/dream/candidates to see latest evaluations.

## Rollback

To disable automation:

```bash
# Systemd timer
sudo systemctl stop dream-auto-eval.timer
sudo systemctl disable dream-auto-eval.timer

# Cron
sudo -u kloros crontab -e  # Comment out the line
```

Manual triggers remain available even when automation is disabled.

## Recommendations

1. **Test First**: Run several manual triggers to verify behavior
2. **Monitor Initially**: Watch logs for first few automated runs
3. **Review Adoptions**: Check `/api/dream/candidates` daily
4. **Baseline Tracking**: Compare new runs to PRE_UNIFICATION_BASELINE.md
5. **Adjust Thresholds**: Modify dream_config.json if admission rates too high/low

## Next Steps

After automation is stable:

1. **KL Divergence**: Add anchor model checks in admit.py
2. **Diversity Metrics**: Implement MinHash/self-BLEU
3. **Domain-Specific Application**: Wire adopted configs to actual KLoROS settings
4. **Regression Detection**: Monitor for performance degradation
5. **A/B Testing**: Shadow deployments for high-impact candidates
