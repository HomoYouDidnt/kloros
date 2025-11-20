# Phase 4: Orchestrator Timer Disablement Procedure

**Date:** 2025-11-14
**Phase:** Phase 4 - KLoROS Policy Engine Deployment
**Status:** Ready for execution (NOT YET EXECUTED)

## Overview

This document describes the procedure to disable the legacy oneshot orchestrator timer and transition to the event-driven policy engine architecture.

## Current State

The oneshot orchestrator is currently running via systemd timer:
- **Timer:** `/etc/systemd/system/kloros-orchestrator.timer`
- **Service:** `/etc/systemd/system/kloros-orchestrator.service`
- **Frequency:** Every 60 seconds
- **Status:** Active (enabled)

## Target State

After Phase 4 deployment:
- **Timer:** Stopped and disabled
- **Service:** Inactive (only timer is disabled)
- **Policy Engine:** Running as continuous daemon
- **Orchestrator Monitor:** Running as continuous daemon

## Disablement Commands

To disable the orchestrator timer, execute:

```bash
sudo systemctl stop kloros-orchestrator.timer
sudo systemctl disable kloros-orchestrator.timer
sudo systemctl daemon-reload
```

To verify:

```bash
systemctl status kloros-orchestrator.timer
systemctl is-enabled kloros-orchestrator.timer
```

Expected output:
- Status: `inactive (dead)`
- Enabled: `disabled`

## Rollback Procedure

If issues are discovered after disabling the timer:

```bash
sudo systemctl enable kloros-orchestrator.timer
sudo systemctl start kloros-orchestrator.timer
sudo systemctl stop kloros-policy-engine.service
```

This restores the oneshot orchestrator and stops the policy engine.

## Validation Checklist

Before disabling the timer, ensure:

- [x] KLoROS Policy Engine implemented (`kloros_policy_engine.py`)
- [x] Policy Engine tests passing
- [x] Policy Engine systemd service created
- [x] Orchestrator Monitor is running and emitting `Q_PROMOTIONS_DETECTED`
- [ ] Policy Engine service started and running
- [ ] Verify policy engine subscribes to signals (check logs)
- [ ] Test promotion detection → D-REAM trigger flow
- [ ] Monitor for 24-48 hours before permanent deployment

## Risk Mitigation

**Risk Level:** HIGH - Replaces entire orchestration mechanism

**Mitigations:**
1. Keep oneshot orchestrator service file intact (only disable timer)
2. Test in maintenance mode first
3. Monitor logs closely for 48 hours
4. Verify D-REAM cycles execute on promotions
5. Check for missed intents or promotions

## Timeline

1. **Now:** Policy engine created, tests written, service file created
2. **Next:** Start policy engine service (when ready)
3. **Validation:** Run both systems in parallel briefly
4. **Cutover:** Disable timer after validation
5. **Monitoring:** 48 hour observation period
6. **Phase 5:** Remove legacy files after proven stable

## Notes

- System is currently in maintenance mode
- Timer disablement is reversible
- Do NOT delete service/timer files yet (Phase 5)
- Policy engine handles promotions only; other services are already event-driven

## Related Files

- `/home/kloros/src/kloros/orchestration/kloros_policy_engine.py`
- `/home/kloros/tests/orchestration/test_kloros_policy_engine.py`
- `/etc/systemd/system/kloros-policy-engine.service`
- `/etc/systemd/system/kloros-orchestrator.timer` (to be disabled)
- `/home/kloros/docs/plans/2025-11-14-event-driven-orchestrator-design.md`
