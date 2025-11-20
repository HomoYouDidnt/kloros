# D-REAM Production Mode Configuration

## Status: ✅ ACTIVE

The D-REAM system is now running in **PRODUCTION MODE** with the following settings:

### Configuration Changes (October 7, 2025)
- **dry_run:** `false` - Mutations and deployments are now ENABLED
- **require_approval:** `true` - Still requires explicit approval for critical operations
- **Safety mode:** `LIVE` - System can make actual modifications

### Active Safety Controls
Despite production mode, the following safety measures remain enforced:

#### Resource Limits
- **CPU Time:** 600 seconds (10 minutes) maximum
- **Memory:** 8192 MB (8 GB) maximum
- **File Size:** 100 MB maximum per file
- **Open Files:** 100 file descriptors maximum

#### Path Restrictions
**Allowed Paths:**
- `/home/kloros/src/` - Source code directory
- `/home/kloros/.kloros/` - KLoROS data directory
- `/tmp/dream/` - Temporary working directory

**Blocked Paths:**
- System directories (`/etc`, `/usr`, `/bin`, `/boot`)
- Root directory (`/`)
- Device and process files (`/dev`, `/proc`, `/sys`)
- Root home (`/root`)

#### Operation Controls
- **Network Access:** `false` - No external network operations
- **Approval Required:** `true` - Deployment still needs explicit approval
- **Backup Original:** `true` - Always creates backups before modifications
- **Sign Manifest:** `true` - All changes are cryptographically signed

### Usage in Production Mode

#### Standard Evolution Run
```bash
cd /home/kloros/src/dream
python3 complete_dream_system.py --config configs/default.yaml
```

#### With Financial Regimes
```bash
python3 complete_dream_system.py --regime configs/regimes/example_finance.yaml
```

#### Override to Dry-Run (for testing)
```bash
python3 complete_dream_system.py --dry-run
```

### What This Means

1. **Mutations Enabled:** The system can now generate and apply code modifications
2. **Deployments Active:** Successful evolution candidates can create patches
3. **Safety Maintained:** Path restrictions and resource limits still enforced
4. **Approval Gates:** Critical changes still require human approval
5. **Full Auditing:** All operations logged to telemetry system

### Monitoring

Monitor system activity through:
- **Event logs:** `artifacts/telemetry/events.jsonl`
- **Run manifests:** `artifacts/manifests/`
- **Patch artifacts:** `artifacts/patches/`
- **Backup files:** `artifacts/backups/`

### Emergency Rollback

To return to dry-run mode:
```bash
sudo sed -i 's/dry_run: false/dry_run: true/' configs/default.yaml
sudo sed -i 's/dry_run: false/dry_run: true/' safety/allowlist.yaml
```

---

*Production mode activated by user request on October 7, 2025 at 15:39 UTC*