#!/bin/bash
# Ghost Control Plane - VPS Hardening Script
# Run as root on fresh VPS

set -e

echo "=== GCP VPS Hardening ==="
echo

# 1. Update everything
echo "[1/8] Updating system..."
apt update
apt upgrade -y
apt autoremove -y

# 2. Install security tools
echo "[2/8] Installing security packages..."
apt install -y fail2ban ufw unattended-upgrades

# 3. Create ghost user
echo "[3/8] Creating ghost user..."
if ! id -u ghost &>/dev/null; then
    useradd -m -s /bin/bash ghost
    usermod -aG sudo ghost
    echo "ghost ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ghost
fi

# 4. SSH hardening
echo "[4/8] Hardening SSH..."
cat > /etc/ssh/sshd_config.d/hardening.conf << 'EOF'
# Disable root login
PermitRootLogin no

# Disable password auth (keys only)
PasswordAuthentication no
PubkeyAuthentication yes

# Change port (optional, uncomment if you want)
# Port 2222

# Limit authentication attempts
MaxAuthTries 3

# Disconnect idle sessions
ClientAliveInterval 300
ClientAliveCountMax 2

# Only allow specific users (safer)
AllowUsers ghost
EOF

systemctl restart sshd

# 5. Firewall
echo "[5/8] Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 17472/tcp comment 'GCP Collab'
ufw --force enable

# 6. Fail2ban
echo "[6/8] Setting up fail2ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port = 22
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
EOF

systemctl enable fail2ban
systemctl start fail2ban

# 7. Automatic updates
echo "[7/8] Enabling automatic security updates..."
cat > /etc/apt/apt.conf.d/50unattended-upgrades << 'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::InstallOnShutdown "false";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF

systemctl enable unattended-upgrades
systemctl start unattended-upgrades

# 8. Install GCP
echo "[8/8] Installing Ghost Control Plane..."
su - ghost -c '
    mkdir -p ~/.openclaw/workspace
    cd ~/.openclaw/workspace
    if [ ! -d ghost-control-plane ]; then
        git clone https://github.com/AshmedaiGates/ghost-control-plane.git
    fi
    cd ghost-control-plane
    ./scripts/gcp install
'

echo
echo "=== Hardening Complete ==="
echo
echo "IMPORTANT NEXT STEPS:"
echo "1. Copy your SSH public key to the server:"
echo "   ssh-copy-id ghost@67.217.61.166"
echo
echo "2. Test login: ssh ghost@67.217.61.166"
echo
echo "3. Once confirmed working, root login is disabled"
echo
echo "4. Add to your mesh: gcp mesh-sync add vps-nj 67.217.61.166 --user ghost"
