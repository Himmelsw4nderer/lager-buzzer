#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# ==========================================
# CONFIGURATION - CHANGE THESE TO YOUR LIKING
# ==========================================
HOTSPOT_SSID="lagerbuzzer"
HOTSPOT_PASS="lagerbuzzer"
REPO_URL="https://github.com/Himmelsw4nderer/lager-buzzer.git"
TARGET_DIR="$HOME/lager-buzzer"

echo "=========================================="
echo " Starting Pi Dev Sandbox Setup"
echo "=========================================="

# 1. Ensure Wi-Fi is unblocked and managed by NetworkManager
echo "--> Unblocking and initializing Wi-Fi..."
sudo rfkill unblock wifi
sudo nmcli radio wifi on
sudo nmcli device set wlan0 managed yes

# Delete existing Hotspot profile if it exists to avoid conflicts
sudo nmcli connection delete Hotspot 2>/dev/null || true

# 2. Create the Routed Hotspot
echo "--> Creating Wi-Fi Hotspot: $HOTSPOT_SSID..."
sudo nmcli device wifi hotspot ifname wlan0 ssid "$HOTSPOT_SSID" password "$HOTSPOT_PASS"

# 3. Configure the 192.168.4.1 Subnet & Autoconnect
echo "--> Configuring routing subnet (192.168.4.1/24)..."
sudo nmcli connection modify Hotspot ipv4.addresses 192.168.4.1/24 ipv4.method shared
sudo nmcli connection modify Hotspot connection.autoconnect yes
sudo nmcli connection modify Hotspot connection.autoconnect-priority 100

# Restart hotspot to apply changes
sudo nmcli connection down Hotspot
sudo nmcli connection up Hotspot

# 4. Install Docker
if ! command -v docker &> /dev/null; then
    echo "--> Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
else
    echo "--> Docker is already installed."
fi

# 5. Configure Docker Permissions & Startup
echo "--> Configuring Docker groups and startup..."
sudo usermod -aG docker $USER
sudo systemctl enable docker
sudo systemctl start docker

# 6. Clone Repository and Run Docker Compose
echo "--> Managing project repository..."
if [ -d "$TARGET_DIR" ]; then
    echo "    Directory $TARGET_DIR already exists. Pulling latest updates..."
    cd "$TARGET_DIR"
    git pull
else
    echo "    Cloning $REPO_URL..."
    git clone "$REPO_URL" "$TARGET_DIR"
    cd "$TARGET_DIR"
fi

if [ -d "server" ]; then
    echo "--> Navigating to server directory and starting Docker Compose..."
    cd server

    # webserver/soundboard are gated behind Compose profiles; ensure
    # modes.json is a real file first, otherwise Docker auto-creates the
    # missing bind-mount target as a directory and crash-loops soundboard.
    if [ -d soundboard/modes.json ]; then
        echo "    Found stray directory at soundboard/modes.json, removing..."
        rmdir soundboard/modes.json
    fi
    if [ ! -f soundboard/modes.json ]; then
        echo "    soundboard/modes.json not found, creating from modes.json.example..."
        cp soundboard/modes.json.example soundboard/modes.json
    fi

    # Note: Using 'sudo docker' here because the group policy change
    # for $USER won't fully register until the next terminal session.
    sudo docker compose --profile webserver --profile soundboard up -d
else
    echo "❌ Error: 'server' directory not found inside the cloned repository!"
    exit 1
fi

echo "=========================================="
echo " Setup complete!"
echo " Hotspot '$HOTSPOT_SSID' is live."
echo " Docker containers are initializing in the background."
echo " IMPORTANT: Please log out and log back into SSH to apply Docker permissions."
echo "=========================================="
