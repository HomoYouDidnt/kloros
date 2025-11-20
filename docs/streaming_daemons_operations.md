# Streaming Daemons Operations Manual

**Version:** 1.0  
**Last Updated:** 2025-11-19  
**System:** KLoROS Curiosity Discovery - Event-Driven Architecture

---

## Quick Reference

### Check All Daemons Status
```bash
systemctl status kloros-integration-monitor.service \
                 kloros-capability-discovery.service \
                 kloros-exploration-scanner.service \
                 kloros-knowledge-discovery.service
```

### Restart All Daemons
```bash
sudo systemctl restart kloros-integration-monitor.service \
                       kloros-capability-discovery.service \
                       kloros-exploration-scanner.service \
                       kloros-knowledge-discovery.service
```

### View Live Logs
```bash
journalctl -u kloros-integration-monitor.service -f
```

### Check Memory Usage
```bash
ps aux | grep -E "(integration|capability|exploration|knowledge)_daemon"
```

---

## System Architecture

KLoROS runs 4 streaming daemons that replaced old batch monitors:

| Daemon | Purpose | Type | Memory Limit |
|--------|---------|------|--------------|
| IntegrationMonitor | Broken component wiring detection | File-based | 150MB |
| CapabilityDiscovery | Missing capability detection | File-based | 150MB |
| ExplorationScanner | Hardware/optimization discovery | Timer (300s) | 150MB |
| KnowledgeDiscovery | Documentation gap detection | File-based | 150MB |

**Performance vs Old System:**
- Memory: 400MB (vs 1.5GB+) - 73% reduction
- Latency: <1s (vs 60s batch) - 60x faster
- CPU: 10% constant (vs spiky 100%)

---

## Service Management

### Start/Stop/Restart

```bash
# Start single daemon
sudo systemctl start kloros-integration-monitor.service

# Stop single daemon
sudo systemctl stop kloros-integration-monitor.service

# Restart with state preservation
sudo systemctl restart kloros-integration-monitor.service

# Check if running
systemctl is-active kloros-integration-monitor.service
```

### Enable/Disable Auto-Start

```bash
# Enable (start on boot)
sudo systemctl enable kloros-integration-monitor.service

# Disable
sudo systemctl disable kloros-integration-monitor.service
```

---

## Monitoring & Health Checks

### Quick Health Check Script

```bash
for service in integration-monitor capability-discovery exploration-scanner knowledge-discovery; do
    if systemctl is-active kloros-$service.service > /dev/null; then
        echo "✓ $service is running"
    else
        echo "✗ $service is DOWN"
    fi
done
```

### View Logs

```bash
# Last 50 lines
journalctl -u kloros-integration-monitor.service -n 50 --no-pager

# Live tail
journalctl -u kloros-integration-monitor.service -f

# All daemons together
journalctl -u kloros-integration-monitor.service \
           -u kloros-capability-discovery.service \
           -u kloros-exploration-scanner.service \
           -u kloros-knowledge-discovery.service -f

# Errors only (last hour)
journalctl -u kloros-integration-monitor.service --since "1 hour ago" -p err
```

### Memory Monitoring

```bash
# Current memory usage
systemctl show kloros-integration-monitor.service | grep Memory

# Watch memory in real-time
watch -n 2 "ps aux | grep -E '(integration|capability|exploration|knowledge)_daemon' | grep -v grep"
```

---

## Performance Baselines

### Expected Memory Usage

| Daemon | Baseline | Peak | Hard Limit |
|--------|----------|------|------------|
| IntegrationMonitor | 50-80MB | 120MB | 150MB |
| CapabilityDiscovery | 50-80MB | 120MB | 150MB |
| ExplorationScanner | 5-10MB | 30MB | 150MB |
| KnowledgeDiscovery | 20-40MB | 100MB | 150MB |
| **TOTAL** | **125-210MB** | **370MB** | **600MB** |

### Expected CPU Usage

- Per daemon: 2-5% constant
- Total: ~10% constant
- Spike during scans: 20-30% briefly

### Question Generation Rate

- IntegrationMonitor: 0-5/hour
- CapabilityDiscovery: 0-10/hour
- ExplorationScanner: 0-2 per 5min
- KnowledgeDiscovery: 0-10/hour

---

## Troubleshooting

### Daemon Won't Start

**Check error logs:**
```bash
systemctl status kloros-integration-monitor.service
journalctl -u kloros-integration-monitor.service -n 100 --no-pager
```

**Common causes:**

1. **ChemBus proxy not running**
   ```bash
   systemctl status kloros-chem-proxy.service
   sudo systemctl start kloros-chem-proxy.service
   ```

2. **State file corruption**
   ```bash
   ls /home/kloros/.kloros/*.pkl.corrupted
   # If found, daemon auto-recovers on next start
   ```

3. **Permission errors**
   ```bash
   sudo chown -R kloros:kloros /home/kloros/.kloros/
   ```

### High Memory Usage

**Check actual usage:**
```bash
ps aux | grep integration_monitor_daemon
systemctl show kloros-integration-monitor.service | grep Memory
```

**If >150MB:**

1. Check cache eviction is working:
   ```bash
   journalctl -u kloros-integration-monitor.service | grep -i evict
   ```

2. Restart daemon:
   ```bash
   sudo systemctl restart kloros-integration-monitor.service
   ```

### No Questions Generated

**Check emission:**
```bash
# Are daemons emitting?
journalctl -u kloros-integration-monitor.service | grep "Emitted question"

# Is CuriosityCore subscribed?
journalctl -u kloros.service | grep "Subscribed to curiosity"
```

**Fixes:**

1. Restart ChemBus:
   ```bash
   sudo systemctl restart kloros-chem-proxy.service
   sudo systemctl restart kloros-integration-monitor.service
   ```

2. Trigger test event:
   ```bash
   echo "# test change" >> /home/kloros/src/test_trigger.py
   journalctl -u kloros-integration-monitor.service -f
   ```

### Frequent Restarts

**Check crash logs:**
```bash
journalctl -u kloros-integration-monitor.service | grep -E "(error|exception)" -i -A 5
```

**Common causes:**

1. **OOM kill:**
   ```bash
   dmesg | grep -i "killed process"
   # Daemon hit memory limit and was killed
   ```

2. **Permission errors:**
   ```bash
   sudo -u kloros ls /home/kloros/src
   sudo chown -R kloros:kloros /home/kloros/src
   ```

---

## Emergency Procedures

### All Daemons Down

```bash
# 1. Check ChemBus dependency
systemctl status kloros-chem-proxy.service
sudo systemctl restart kloros-chem-proxy.service

# 2. Wait for ChemBus
sleep 5

# 3. Start all daemons
sudo systemctl start kloros-integration-monitor.service \
                     kloros-capability-discovery.service \
                     kloros-exploration-scanner.service \
                     kloros-knowledge-discovery.service

# 4. Verify
systemctl list-units | grep kloros
```

### System Memory Pressure

```bash
# Stop non-critical daemons
sudo systemctl stop kloros-exploration-scanner.service \
                     kloros-knowledge-discovery.service

# Keep IntegrationMonitor and CapabilityDiscovery running
# (most critical for code quality)

# Monitor recovery
free -h

# Restart when safe
sudo systemctl start kloros-exploration-scanner.service \
                      kloros-knowledge-discovery.service
```

### Daemon CPU Spike (100%)

```bash
# Identify problem daemon
top -u kloros

# Stop it
sudo systemctl stop kloros-integration-monitor.service

# Check logs
journalctl -u kloros-integration-monitor.service -n 200 --no-pager

# Disable until fixed
sudo systemctl disable kloros-integration-monitor.service
```

---

## Maintenance Tasks

### Weekly

```bash
# 1. Verify all running
systemctl list-units | grep kloros

# 2. Check errors
journalctl -u kloros-integration-monitor.service --since "7 days ago" -p err --no-pager

# 3. Check log growth
journalctl --disk-usage
# If >1GB: sudo journalctl --vacuum-time=30d
```

### Monthly

```bash
# 1. Clean old corrupted states
find /home/kloros/.kloros -name "*.pkl.corrupted" -mtime +30 -delete

# 2. Run integration tests
cd /home/kloros/src
/home/kloros/.venv/bin/python3 -m pytest kloros/daemons/test_streaming_daemons_integration.py -v

# 3. Verify log rotation
journalctl --verify
```

---

## File Locations

### Service Files
- `/etc/systemd/system/kloros-integration-monitor.service`
- `/etc/systemd/system/kloros-capability-discovery.service`
- `/etc/systemd/system/kloros-exploration-scanner.service`
- `/etc/systemd/system/kloros-knowledge-discovery.service`

### State Files
- `/home/kloros/.kloros/integration_monitor_state.pkl`
- `/home/kloros/.kloros/capability_discovery_state.pkl`
- `/home/kloros/.kloros/exploration_scanner_state.pkl`
- `/home/kloros/.kloros/knowledge_discovery_state.pkl`

### Daemon Code
- `/home/kloros/src/kloros/daemons/base_streaming_daemon.py`
- `/home/kloros/src/kloros/daemons/integration_monitor_daemon.py`
- `/home/kloros/src/kloros/daemons/capability_discovery_daemon.py`
- `/home/kloros/src/kloros/daemons/exploration_scanner_daemon.py`
- `/home/kloros/src/kloros/daemons/knowledge_discovery_daemon.py`

### Tests
- `/home/kloros/src/kloros/daemons/test_streaming_daemons_integration.py`
- `/home/kloros/src/kloros/daemons/test_*_daemon.py` (unit tests)

---

## Additional Resources

- Architecture: `/home/kloros/docs/streaming_daemon_architecture_design.md`
- Implementation Plan: `/tmp/streaming_daemons_implementation_plan.md`
- Session Documentation: `/home/kloros/docs/`

---

**End of Operations Manual v1.0**
