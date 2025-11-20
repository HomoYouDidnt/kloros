# KLoROS Actions Registry

Complete list of actions KLoROS can execute autonomously.

## Currently Implemented

### reduce_investigation_concurrency ✅
- **What:** Emits INVESTIGATION_THROTTLE_REQUEST to reduce concurrency
- **Limitations:** Only prevents NEW threads, doesn't clear EXISTING ones
- **Use when:** Investigation consumer accumulating threads
- **Why it keeps failing:** You already have 794 threads stuck. This only stops MORE from accumulating.

## Read-Only (Always Safe)

### measure, collect, record ✅
- Metrics collected automatically before/after execution

### wait, delay, stabilize ✅
- 60-second wait for system stabilization

### validate, verify, check ✅
- Automatic before/after metric comparison

## NOT Implemented (Don't Use)

- `restart_service` - Would fix stuck threads but not yet implemented
- `execute_command` - Security risk
- `clear_queue` - Not implemented

## Why Throttling Alone Fails

**The Problem:**
- investigation_consumer has 794 threads ALREADY stuck
- Throttling prevents thread 795, 796, 797...
- But doesn't clear threads 1-794

**What You Need:**
- `restart_service` to clear existing threads
- Then throttle to prevent recurrence
- But restart not implemented yet

**Current Limitation:**
You can only slow the bleeding, not stop it.
