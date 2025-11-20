# ChemBus Proxy Service Migration

**Date:** 2025-11-17
**Migration:** spica-chem-proxy → kloros-chem-proxy
**Status:** Complete

## Executive Summary

Consolidated dual ChemBus proxy services (spica-chem-proxy and kloros-chem-proxy) into single unified kloros-chem-proxy service to eliminate port conflicts and align with current KLoROS naming conventions.

## Background

### The Problem

Two systemd services were running identical ChemBus proxy code (kloros.orchestration.chem_proxy) on the same TCP ports:

- **spica-chem-proxy.service** (created 2025-11-07)
  - Serving 7 older services (curiosity, orchestration, zooids)
  - Explicit environment variables for ports
  - Proper module invocation syntax

- **kloros-chem-proxy.service** (created 2025-11-16, 9 days later)
  - Serving 4 newer consciousness services
  - No explicit environment variables
  - Direct file path invocation

**Conflict:** Both services attempting to bind tcp://127.0.0.1:5556 (XSUB) and tcp://127.0.0.1:5557 (XPUB), causing kloros-chem-proxy to crash-loop.

### Discovery

The issue was discovered during autonomous investigation monitoring:
- KLoROS self-reported chem-proxy failures
- Investigation revealed port binding conflicts
- Manual analysis confirmed duplicate service architecture

## Architecture Decision

**Decision:** Migrate all services to kloros-chem-proxy as the unified ChemBus proxy.

**Rationale:**
1. **Naming Convention:** kloros-chem-proxy aligns with current KLoROS branding (not SPICA)
2. **Timeline:** kloros-chem-proxy was created more recently (Nov 16 vs Nov 7)
3. **Architecture:** Single proxy serves all services more efficiently
4. **Maintainability:** One service definition to manage

## ChemBus Architecture

The ChemBus (Chemical Signal Bus) is a ZeroMQ-based publish/subscribe message bus enabling inter-service communication within KLoROS.

**Core Components:**
- **XSUB socket** (tcp://127.0.0.1:5556): Publishers connect here
- **XPUB socket** (tcp://127.0.0.1:5557): Subscribers connect here
- **chem_proxy.py**: Forwarder bridging XSUB ↔ XPUB

**Implementation:** /home/kloros/src/kloros/orchestration/chem_proxy.py

## Migration Procedure

### 1. Service Identification (Completed)

Identified 8 services depending on spica-chem-proxy:

**Orchestration Services:**
- kloros-capability-integrator.service
- kloros-chembus-historian.service
- kloros-curiosity-core-consumer.service
- kloros-intent-router.service
- kloros-orchestrator-monitor.service
- kloros-winner-deployer.service

**Zooid Services (Template-based):**
- zooid-backpressure-balancer@.service
- zooid-latency-tracker@.service

### 2. Dependency Update (Completed)

Updated all service files to reference kloros-chem-proxy using sed:

Changed Directives:
- After=spica-chem-proxy.service → After=kloros-chem-proxy.service
- Requires=spica-chem-proxy.service → Requires=kloros-chem-proxy.service
- Wants=spica-chem-proxy.service → Wants=kloros-chem-proxy.service

### 3. Service Transition (Completed)

Commands executed:
- sudo systemctl daemon-reload
- sudo systemctl stop spica-chem-proxy.service
- sudo systemctl disable spica-chem-proxy.service
- sudo systemctl start kloros-chem-proxy.service

Result: kloros-chem-proxy running successfully (PID 1939964)

### 4. Service Verification (Completed)

Restarted and verified dependent services:
- kloros-curiosity-core-consumer.service
- kloros-intent-router.service
- kloros-orchestrator-monitor.service
- kloros-winner-deployer.service

Status: All services operational with kloros-chem-proxy dependency.

## Post-Migration State

### Active Service

kloros-chem-proxy.service:
- Description: KLoROS ChemBus Proxy (ZMQ message bus)
- User: kloros
- WorkingDirectory: /home/kloros/src
- ExecStart: /home/kloros/.venv/bin/python -u kloros/orchestration/chem_proxy.py
- Restart: always (10s delay)
- Location: /etc/systemd/system/kloros-chem-proxy.service

### Deprecated Service

spica-chem-proxy.service:
- Status: Stopped and disabled
- Action: Retained for historical reference but not active
- Location: /etc/systemd/system/spica-chem-proxy.service

### Dependent Services

All 8 migrated services now use kloros-chem-proxy.service dependency:

Orchestration:
- kloros-capability-integrator
- kloros-chembus-historian
- kloros-curiosity-core-consumer
- kloros-intent-router
- kloros-orchestrator-monitor
- kloros-winner-deployer

Zooids:
- zooid-backpressure-balancer@
- zooid-latency-tracker@

Consciousness Services (already using kloros-chem-proxy):
- kloros-consciousness-healing
- kloros-consciousness-cognitive-actions
- kloros-consciousness-cognitive-orchestrator
- kloros-consciousness-state-publisher

## Verification Commands

Check proxy status:
systemctl status kloros-chem-proxy.service

Check dependent services:
systemctl list-dependencies kloros-chem-proxy.service --reverse

Monitor ChemBus activity:
journalctl -u kloros-chem-proxy.service -f

Verify port bindings:
ss -tlnp | grep -E "5556|5557"

## Rollback Procedure

If rollback is required:

1. Stop kloros-chem-proxy
2. Revert sed changes to service files
3. Reload daemon and restart spica-chem-proxy

## Related Documentation

- ChemBus Implementation: /home/kloros/src/kloros/orchestration/chem_proxy.py
- System Architecture: /home/kloros/docs/SYSTEM_ARCHITECTURE_OVERVIEW.md
- KLoROS Functional Design: /home/kloros/docs/KLOROS_FUNCTIONAL_DESIGN.md

## Migration Timeline

- 2025-11-07: spica-chem-proxy.service created
- 2025-11-16: kloros-chem-proxy.service created (port conflict begins)
- 2025-11-17: Migration executed and completed

## Notes

- Zero downtime for services during migration (sequential restart)
- No code changes required, only systemd dependency updates
- Port conflict resolution validates single-proxy architecture
- Autonomous investigation system successfully flagged the issue
