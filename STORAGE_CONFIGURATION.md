# KLoROS Storage Configuration

**Date:** 2025-10-27
**Storage Added:** Samsung SSD 870 EVO 500GB
**Status:** Available for allocation

---

## Storage Layout

### Primary Drive (NVMe)
- **Device:** `/dev/nvme0n1p2`
- **Capacity:** 221GB
- **Mount:** `/`
- **Usage:** System, applications, user data
- **Current Usage:** 61% (84GB free)

### Additional Storage (SSD)
- **Device:** `/dev/sda1`
- **Capacity:** 458GB
- **Mount:** `/mnt/storage`
- **Filesystem:** ext4
- **Label:** `kloros-storage`
- **UUID:** `537a9067-86f7-4f9e-b4f5-6d2406d51a7d`
- **Mount Options:** `defaults,noatime`
- **Owner:** `kloros:kloros`
- **Permissions:** 755
- **Current Usage:** <1% (435GB available)
- **Status:** ✅ **Mounted and ready - unallocated**

---

## Auto-Mount Configuration

### /etc/fstab Entry
```fstab
# KLoROS additional storage (Samsung SSD 870 EVO 500GB)
UUID=537a9067-86f7-4f9e-b4f5-6d2406d51a7d /mnt/storage ext4 defaults,noatime 0 2
```

**Mount Options:**
- `defaults`: Standard mount options (rw, suid, dev, exec, auto, nouser, async)
- `noatime`: Don't update file access times (improves performance)
- `0`: No dump backup
- `2`: fsck pass 2 (check after root filesystem)

---

## Discovery

Storage metadata is available at:
- **Human-readable:** `/mnt/storage/README.md`
- **Machine-readable:** `/mnt/storage/storage_manifest.json`

### Storage Manifest
```json
{
  "storage_id": "kloros-storage-001",
  "mount_point": "/mnt/storage",
  "capacity_gb": 458,
  "available_gb": 435,
  "status": "available",
  "allocated": false,
  "purpose": null
}
```

---

## Suggested Uses

This storage is ready for KLoROS to allocate based on autonomous decision-making:

### High-Priority Candidates
- **SPICA instance overflow** - When retention limits aren't enough
- **Model cache** - HuggingFace, Ollama models (currently 22GB in /var/lib/ollama)
- **Experiment artifacts** - Long-term D-REAM results storage
- **Docker volumes** - Isolate container storage from system drive

### Medium-Priority Candidates
- **Large datasets** - Training/test data for ML experiments
- **Log archives** - Long-term log retention
- **Backup snapshots** - System state before major changes

### Low-Priority Candidates
- **Pip/cache overflow** - Only if cache exceeds reasonable limits
- **Build artifacts** - Compilation outputs, test results

---

## Access and Permissions

### Verification
```bash
# Check mount status
df -h /mnt/storage

# Verify ownership
ls -ld /mnt/storage

# Test write access
sudo -u kloros touch /mnt/storage/test && sudo -u kloros rm /mnt/storage/test
```

### Creating Directories
```bash
# As kloros user
mkdir /mnt/storage/my_directory

# With specific permissions
mkdir -m 755 /mnt/storage/shared_data
```

---

## Maintenance

### Check Storage Health
```bash
# Disk usage
df -h /mnt/storage

# Directory breakdown
du -sh /mnt/storage/*

# Filesystem check (unmount first)
sudo umount /mnt/storage
sudo fsck.ext4 -f /dev/sda1
sudo mount /mnt/storage
```

### Manual Mount/Unmount
```bash
# Mount
sudo mount /mnt/storage

# Unmount (ensure nothing is using it)
sudo umount /mnt/storage
```

### Validate fstab
```bash
# Test all fstab entries
sudo mount -a && echo "OK" || echo "ERROR in fstab"
```

---

## Recovery Scenarios

### If Storage Drive Fails
1. System will boot normally (root on NVMe)
2. Only `/mnt/storage` will be unavailable
3. Remove or comment out fstab entry to prevent boot delays
4. Replace drive and restore from backups if needed

### If Mount Fails at Boot
```bash
# Check fstab syntax
sudo cat /etc/fstab | grep kloros-storage

# Manual mount
sudo mount UUID=537a9067-86f7-4f9e-b4f5-6d2406d51a7d /mnt/storage

# Check systemd mount unit
systemctl status mnt-storage.mount

# View logs
journalctl -u mnt-storage.mount
```

### Emergency Unmount
```bash
# If storage is causing issues
sudo umount -f /mnt/storage

# Comment out from fstab
sudo sed -i 's/^UUID=537a9067-86f7/#&/' /etc/fstab
```

---

## Integration Notes

### For Autonomous Systems
Storage manifest is available for automated discovery:
```python
import json
from pathlib import Path

manifest = json.loads(Path("/mnt/storage/storage_manifest.json").read_text())
if manifest["allocated"] == False and manifest["available_gb"] > 100:
    # Storage is available for use
    purpose = determine_allocation()  # Your logic here
    allocate_storage(manifest["mount_point"], purpose)
```

### For SPICA
To use this storage for instances, update `spica_spawn.py`:
```python
INSTANCES = Path("/mnt/storage/spica_instances")  # Instead of experiments/spica/instances
```

### For Ollama Models
To relocate model storage:
```bash
sudo systemctl stop ollama
sudo mv /var/lib/ollama /mnt/storage/ollama
sudo ln -s /mnt/storage/ollama /var/lib/ollama
sudo systemctl start ollama
```

---

## Capacity Planning

| Scenario | Estimated Use | Remaining |
|----------|--------------|-----------|
| Current (empty) | 2MB | 435GB |
| SPICA (10 instances @ 5GB) | 50GB | 385GB |
| Ollama models (relocated) | 22GB | 413GB |
| Combined (SPICA + Ollama) | 72GB | 363GB |
| Full allocation (80% policy) | 366GB | 69GB |

**Recommendation:** Keep 20% (92GB) reserved for filesystem overhead and future needs.

---

## Performance Characteristics

- **Type:** SATA SSD (Samsung 870 EVO)
- **Expected Sequential Read:** ~560 MB/s
- **Expected Sequential Write:** ~530 MB/s
- **Expected Random IOPS:** ~98,000 read / ~88,000 write
- **Interface:** SATA 6 Gb/s
- **Mount Options:** `noatime` enabled for reduced I/O overhead

---

## Testing

### Persistence Test
```bash
# Reboot and verify auto-mount
sudo reboot

# After reboot, verify
df -h /mnt/storage
cat /mnt/storage/README.md
```

### Write Performance Test
```bash
# Test write speed (1GB)
dd if=/dev/zero of=/mnt/storage/test.bin bs=1M count=1000 conv=fdatasync

# Cleanup
rm /mnt/storage/test.bin
```

### Storage Integrity Test
```bash
# Create test file with known hash
echo "test data" | sudo -u kloros tee /mnt/storage/test.txt
sha256sum /mnt/storage/test.txt

# Remount and verify
sudo umount /mnt/storage && sudo mount /mnt/storage
sha256sum /mnt/storage/test.txt  # Should match

# Cleanup
rm /mnt/storage/test.txt
```

---

## Monitoring

### Add to System Monitoring
```bash
# Check if storage is mounted
findmnt /mnt/storage || echo "WARNING: Storage not mounted"

# Alert if usage exceeds threshold
USAGE=$(df /mnt/storage | awk 'NR==2 {print $5}' | sed 's/%//')
[ "$USAGE" -gt 80 ] && echo "WARNING: Storage at ${USAGE}%"
```

### Log Rotation for Storage
If storing logs on this drive:
```bash
# /etc/logrotate.d/kloros-storage
/mnt/storage/logs/*.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
}
```

---

## Sign-Off

- **Storage Provisioned:** 2025-10-27 03:26 UTC
- **Capacity:** 458GB (435GB available)
- **Auto-Mount:** Configured in /etc/fstab
- **Permissions:** kloros:kloros (755)
- **Allocation Status:** **Unallocated - awaiting KLoROS decision**
- **Production Ready:** YES

**Next Steps:**
1. KLoROS can discover storage via `/mnt/storage/storage_manifest.json`
2. Allocate storage based on system needs and priorities
3. Update `storage_manifest.json` when allocations are made
4. Monitor usage and adjust allocations as needed
