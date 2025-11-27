#!/bin/bash
set -e

echo "Installing KLoROS Introspection Daemon..."

# Copy service file
sudo cp /home/kloros/systemd/kloros-introspection.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable kloros-introspection.service

echo "✓ Service installed and enabled"
echo ""
echo "To start the service:"
echo "  sudo systemctl start kloros-introspection"
echo ""
echo "To check status:"
echo "  sudo systemctl status kloros-introspection"
echo ""
echo "To view logs:"
echo "  journalctl -u kloros-introspection -f"
