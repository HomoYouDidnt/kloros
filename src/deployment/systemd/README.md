# KLoROS Affective Action System - Systemd Services

Production deployment configuration for KLoROS's autonomous affective action system.

## Overview

Four independent daemons provide autonomous responses to KLoROS's emotional states:

| Service | Tier | Signals | Purpose |
|---------|------|---------|---------|
| kloros-emergency-brake | 0 | PANIC, CRITICAL_FATIGUE | Halt processing |
| kloros-system-healing | 1 | HIGH_RAGE, ERRORS | Emit HEAL_REQUEST |
| kloros-cognitive-actions | 2 | MEMORY_PRESSURE | Episodic memory ops |
| kloros-heal-executor | - | HEAL_REQUEST | Execute playbooks |

## Dependencies

All services require:
- `kloros-chem-proxy.service` (ChemBus message bus)
- Network connectivity

## Installation

```bash
# Copy service files to systemd directory
sudo cp deployment/systemd/*.service /etc/systemd/system/

# Reload systemd to recognize new services
sudo systemctl daemon-reload

# Enable services for automatic startup
sudo systemctl enable kloros-emergency-brake.service
sudo systemctl enable kloros-system-healing.service
sudo systemctl enable kloros-cognitive-actions.service
sudo systemctl enable kloros-heal-executor.service

# Start services
sudo systemctl start kloros-emergency-brake.service
sudo systemctl start kloros-system-healing.service
sudo systemctl start kloros-cognitive-actions.service
sudo systemctl start kloros-heal-executor.service
```

## Management

### Check service status
```bash
sudo systemctl status kloros-emergency-brake
sudo systemctl status kloros-system-healing
sudo systemctl status kloros-cognitive-actions
sudo systemctl status kloros-heal-executor
```

### View logs
```bash
# Real-time logs
journalctl -u kloros-emergency-brake -f
journalctl -u kloros-system-healing -f
journalctl -u kloros-cognitive-actions -f
journalctl -u kloros-heal-executor -f

# Recent logs
journalctl -u kloros-emergency-brake -n 100
journalctl -u kloros-system-healing -n 100
journalctl -u kloros-cognitive-actions -n 100
journalctl -u kloros-heal-executor -n 100
```

### Restart services
```bash
sudo systemctl restart kloros-emergency-brake
sudo systemctl restart kloros-system-healing
sudo systemctl restart kloros-cognitive-actions
sudo systemctl restart kloros-heal-executor
```

### Stop services
```bash
sudo systemctl stop kloros-emergency-brake
sudo systemctl stop kloros-system-healing
sudo systemctl stop kloros-cognitive-actions
sudo systemctl stop kloros-heal-executor
```

## Action Logs

Additional action logs (beyond journalctl):

- Emergency brake activations: `/tmp/kloros_emergency_brake_active`
- Healing actions: `/tmp/kloros_healing_actions.log`
- Cognitive actions: `/tmp/kloros_cognitive_actions.log`

## Startup Order

1. `kloros-chem-proxy.service` (ChemBus proxy)
2. Affective subscribers (parallel startup, wait for ChemBus)
3. Main KLoROS service (begins emitting signals)

All services wait for `kloros-chem-proxy.service` via `After=` and `Requires=` directives.

## Restart Behavior

Services automatically restart on failure with 10-second delay:
- `Restart=always`
- `RestartSec=10`

## Rollback

To disable a service:
```bash
sudo systemctl stop kloros-{service-name}
sudo systemctl disable kloros-{service-name}
```

To completely remove:
```bash
sudo systemctl stop kloros-{service-name}
sudo systemctl disable kloros-{service-name}
sudo rm /etc/systemd/system/kloros-{service-name}.service
sudo systemctl daemon-reload
```

## Environment Variables

Set in service file `[Service]` section:

- `PYTHONPATH=/home/kloros/src` (required for module imports)
- `KLR_HEAL_DRY_RUN=1` (optional, enables dry-run mode for heal_executor)
- `KLR_ENABLE_AFFECT=0` (optional, disables consciousness signal emission)

## Verification

After installation, verify all services are running:
```bash
systemctl list-units 'kloros-*' --type=service
```

Expected output shows all 4 services in `active (running)` state.
