#!/bin/bash

echo "Setting up Claude C2C automatic save/restore..."
echo ""

echo "1. Creating bashrc hook for claude_temp user..."

BASHRC_HOOK='
# Claude C2C auto-restore on login
if [ -f /home/kloros/bin/claude_c2c_startup.sh ]; then
    /home/kloros/bin/claude_c2c_startup.sh
fi
'

if ! grep -q "Claude C2C auto-restore" /home/claude_temp/.bashrc 2>/dev/null; then
    echo "$BASHRC_HOOK" | sudo tee -a /home/claude_temp/.bashrc > /dev/null
    echo "   ✅ Added to /home/claude_temp/.bashrc"
else
    echo "   ⚠️  Already present in /home/claude_temp/.bashrc"
fi

echo ""
echo "2. Creating logout hook for claude_temp user..."

BASH_LOGOUT='
# Claude C2C auto-save on logout
if [ -f /home/kloros/claude_c2c_save_on_exit.sh ]; then
    /home/kloros/claude_c2c_save_on_exit.sh
fi
'

if [ ! -f /home/claude_temp/.bash_logout ]; then
    echo "$BASH_LOGOUT" | sudo tee /home/claude_temp/.bash_logout > /dev/null
    sudo chown claude_temp:claude_temp /home/claude_temp/.bash_logout
    echo "   ✅ Created /home/claude_temp/.bash_logout"
else
    if ! grep -q "Claude C2C auto-save" /home/claude_temp/.bash_logout; then
        echo "$BASH_LOGOUT" | sudo tee -a /home/claude_temp/.bash_logout > /dev/null
        echo "   ✅ Added to /home/claude_temp/.bash_logout"
    else
        echo "   ⚠️  Already present in /home/claude_temp/.bash_logout"
    fi
fi

echo ""
echo "3. Setting up systemd user service (optional, for kloros user)..."

SYSTEMD_DIR="/home/kloros/.config/systemd/user"
if [ -d "$SYSTEMD_DIR" ]; then
    if [ -f "$SYSTEMD_DIR/claude-c2c-save.service" ]; then
        systemctl --user daemon-reload 2>/dev/null
        systemctl --user enable claude-c2c-save.service 2>/dev/null
        echo "   ✅ Enabled systemd service for kloros user"
    fi
else
    echo "   ⚠️  Systemd user directory not found (skip)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ Claude C2C Automatic Save/Restore Setup Complete!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "How it works:"
echo "  • On claude_temp login → Automatically displays restore prompt"
echo "  • On claude_temp logout → Automatically saves session state"
echo ""
echo "Manual commands still available:"
echo "  • Save: python3 /home/kloros/src/c2c/auto_restore_claude.py save"
echo "  • Restore: python3 /home/kloros/src/c2c/auto_restore_claude.py restore"
echo ""
echo "Test it:"
echo "  1. Exit this session"
echo "  2. Start new session as claude_temp"
echo "  3. See automatic restore message"
echo ""
