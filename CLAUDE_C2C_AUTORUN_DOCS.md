# Claude C2C Automatic Save/Restore Service

**Status:** ✅ **OPERATIONAL**

## Overview

Automatic session state preservation for Claude Code across the `claude_temp` user lifecycle.

## How It Works

```
┌─ On Login (claude_temp) ─────────────────────────────────┐
│ 1. Shell loads ~/.bashrc                                 │
│ 2. Runs /home/kloros/bin/claude_c2c_startup.sh          │
│ 3. Displays previous session context notification        │
│ 4. Writes full context to /tmp/claude_c2c_restore_*.txt │
└───────────────────────────────────────────────────────────┘

┌─ On Logout (claude_temp) ────────────────────────────────┐
│ 1. Shell runs ~/.bash_logout                             │
│ 2. Executes /home/kloros/claude_c2c_save_on_exit.sh     │
│ 3. Saves current session state to cache                  │
│ 4. Session state preserved for next login                │
└───────────────────────────────────────────────────────────┘
```

## Installation

Already installed! Run the setup script anytime to verify:

```bash
/home/kloros/setup_claude_c2c_autorun.sh
```

## What Gets Saved

When a `claude_temp` session ends, the system captures:
- Completed tasks with results
- Key discoveries
- Current work context
- System state
- Active files being worked on
- Metadata (operator, timestamp, etc.)

## What Gets Restored

When a new `claude_temp` session starts, you'll see:

```
═══════════════════════════════════════════════════════════════
📋 Claude C2C: Previous session context available
═══════════════════════════════════════════════════════════════

View with: cat /tmp/claude_c2c_restore_latest.txt
Or run: python3 /home/kloros/src/c2c/auto_restore_claude.py restore
```

The full context is saved to `/tmp/claude_c2c_restore_latest.txt` for easy access.

## Files Created

**Shell Hooks:**
- `/home/claude_temp/.bashrc` - Added C2C restore hook (at end)
- `/home/claude_temp/.bash_logout` - Added C2C save hook (at end)

**Scripts:**
- `/home/kloros/bin/claude_c2c_startup.sh` - Displays restore notification on login
- `/home/kloros/claude_c2c_save_on_exit.sh` - Saves state on logout
- `/home/kloros/setup_claude_c2c_autorun.sh` - Installation/verification script

**Systemd Services (optional, for kloros user):**
- `/home/kloros/.config/systemd/user/claude-c2c-save.service`
- `/home/kloros/.config/systemd/user/claude-c2c-restore.service`

## Manual Commands

You can still manually trigger save/restore:

```bash
# Save current session
python3 /home/kloros/src/c2c/auto_restore_claude.py save

# Restore previous session
python3 /home/kloros/src/c2c/auto_restore_claude.py restore

# List all sessions
python3 /home/kloros/src/c2c/auto_restore_claude.py list
```

## Usage Workflow

### Normal Flow (Automatic)

1. **Start new claude_temp session**
   - Notification appears automatically
   - Context file saved to `/tmp/claude_c2c_restore_latest.txt`

2. **View the context**
   ```bash
   cat /tmp/claude_c2c_restore_latest.txt
   ```

3. **Provide to Claude**
   Copy the contents and say:
   > "Here's the context from my previous session: [paste context]"

4. **Work on tasks**
   Claude now has full understanding of previous work

5. **Exit session**
   - State automatically saved
   - Ready for next session

### If Notification Doesn't Appear

The notification only appears if:
- There is a previous session saved
- The session is less than 60 minutes old (configurable)
- The scripts have correct permissions

To manually check:
```bash
python3 /home/kloros/src/c2c/auto_restore_claude.py restore
```

## Troubleshooting

### No notification on login

**Check if session exists:**
```bash
python3 /home/kloros/src/c2c/auto_restore_claude.py list
```

**Check script permissions:**
```bash
ls -la /home/kloros/bin/claude_c2c_startup.sh
# Should be: -rwxr-xr-x
```

**Check bashrc hook:**
```bash
tail -5 /home/claude_temp/.bashrc
# Should show "Claude C2C auto-restore" section
```

### Session not saving on logout

**Check logout hook:**
```bash
cat /home/claude_temp/.bash_logout
# Should show "Claude C2C auto-save" section
```

**Check save script permissions:**
```bash
ls -la /home/kloros/claude_c2c_save_on_exit.sh
# Should be: -rwxr-xr-x
```

**Manual save test:**
```bash
python3 /home/kloros/src/c2c/auto_restore_claude.py save
```

### Stale sessions (too old)

Sessions older than 60 minutes are filtered out by default. To see all sessions:
```bash
python3 -c "
from src.c2c import ClaudeC2CManager
manager = ClaudeC2CManager()
sessions = manager.list_sessions(max_age_minutes=999999)
for s in sessions:
    print(f\"{s['session_id']}: {s['timestamp']}\")
"
```

## Configuration

### Change session TTL

Edit `/home/kloros/src/c2c/auto_restore_claude.py`:
```python
# In restore_latest_session()
latest = manager.get_latest_session()  # Uses default 60min

# To use longer TTL:
latest = manager.load_session_state(session_id, max_age_minutes=180)  # 3 hours
```

### Disable for specific user

Remove hooks from `.bashrc` and `.bash_logout`:
```bash
# Edit and remove Claude C2C sections
sudo nano /home/claude_temp/.bashrc
sudo nano /home/claude_temp/.bash_logout
```

### Add for additional users

Run setup and specify different user:
```bash
# Modify setup script to target different user
# Or manually add hooks to their .bashrc/.bash_logout
```

## Integration with Claude Code

When you start a new Claude Code session:

1. You'll see the notification banner
2. View the full context: `cat /tmp/claude_c2c_restore_latest.txt`
3. Copy the contents
4. In your first message to Claude, include:
   ```
   Here's the context from my previous session:

   [paste full context]

   Please continue from where we left off.
   ```

Claude will have complete understanding of:
- What was accomplished
- What was discovered
- What you were working on
- System state
- Relevant files

## Cache Storage

**Location:** `/home/kloros/.kloros/c2c_caches/claude_sessions/`

Each session is a JSON file with:
- Completed tasks
- Key discoveries
- Current context
- System state
- Active files
- Timestamp and metadata

**Cleanup:**
Old sessions (>60min by default) are automatically filtered from listings but not deleted. To manually clean:
```bash
find /home/kloros/.kloros/c2c_caches/claude_sessions/ -name "*.json" -mtime +7 -delete
```

## Benefits

✅ **Zero Manual Steps**: Automatic save on logout, restore on login
✅ **No Context Loss**: Perfect continuity across session boundaries
✅ **Instant Resume**: Full context available immediately
✅ **Non-Intrusive**: Just a notification banner, doesn't interrupt workflow
✅ **Fallback Available**: Manual commands always work if automation fails

## Verification

To verify the system is working:

1. **Save a test session:**
   ```bash
   python3 /home/kloros/src/c2c/auto_restore_claude.py save
   ```

2. **Check it was saved:**
   ```bash
   python3 /home/kloros/src/c2c/auto_restore_claude.py list
   ```

3. **Test restore:**
   ```bash
   python3 /home/kloros/src/c2c/auto_restore_claude.py restore
   ```

4. **Check startup notification:**
   ```bash
   /home/kloros/bin/claude_c2c_startup.sh
   ```

All should complete successfully.

---

**Implementation Date:** 2025-11-04
**Status:** Production-ready
**Automatic Operation:** ✅ Enabled for claude_temp user
