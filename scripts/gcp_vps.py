#!/usr/bin/env python3
"""
Ghost Control Plane - VPS Provisioner
Automated setup for new GCP mesh nodes
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

# Bootstrap script that gets run on the remote VPS
BOOTSTRAP_SCRIPT = '''#!/bin/bash
set -e

echo "=== Ghost Control Plane - VPS Bootstrap ==="
echo

# Detect distro
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
else
    echo "Cannot detect distro"
    exit 1
fi

echo "[1/6] Updating system ($DISTRO)..."
if command -v apt &> /dev/null; then
    apt update && apt upgrade -y
    apt install -y python3 python3-pip git curl wget tmux htop iotop rsync
elif command -v dnf &> /dev/null; then
    dnf update -y
    dnf install -y python3 python3-pip git curl wget tmux htop iotop rsync
elif command -v pacman &> /dev/null; then
    pacman -Syu --noconfirm
    pacman -S --noconfirm python python-pip git curl wget tmux htop iotop rsync
fi

echo "[2/6] Creating ghost user..."
if ! id -u ghost &>/dev/null; then
    useradd -m -s /bin/bash ghost
    usermod -aG sudo ghost
    echo "ghost ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ghost
fi

echo "[3/6] Installing Ghost Control Plane..."
su - ghost -c '
    mkdir -p ~/.openclaw/workspace
    cd ~/.openclaw/workspace
    
    if [ ! -d ghost-control-plane ]; then
        git clone https://github.com/AshmedaiGates/ghost-control-plane.git
    fi
    
    cd ghost-control-plane
    ./scripts/gcp install
'

echo "[4/6] Setting up systemd services..."
su - ghost -c '
    mkdir -p ~/.config/systemd/user
    cp ~/.openclaw/workspace/ghost-control-plane/systemd/user/*.service ~/.config/systemd/user/ 2>/dev/null || true
    cp ~/.openclaw/workspace/ghost-control-plane/systemd/user/*.timer ~/.config/systemd/user/ 2>/dev/null || true
    systemctl --user daemon-reload
'

echo "[5/6] Installing mesh collaboration server..."
su - ghost -c '
    # Create systemd service for collab server
    mkdir -p ~/.config/systemd/user
    cat > ~/.config/systemd/user/gcp-collab.service << EOF
[Unit]
Description=Ghost Control Plane Collaboration Server
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/bin/gcp collab server
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable gcp-collab.service
'

echo "[6/6] Configuring firewall..."
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp
    ufw allow 17472/tcp  # GCP collab port
    ufw --force enable
elif command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --add-port=22/tcp
    firewall-cmd --permanent --add-port=17472/tcp
    firewall-cmd --reload
fi

echo
echo "=== Bootstrap Complete ==="
echo "GCP is installed for user: ghost"
echo "Mesh collab port: 17472"
echo "Add this node to your mesh with:"
echo "  gcp mesh-sync add <name> <this-ip> --user ghost"
'''

def run(cmd, check=True):
    """Run shell command"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    return result.stdout.strip()

def generate_ssh_key():
    """Generate SSH key for VPS access if not exists"""
    key_path = Path.home() / '.ssh' / 'gcp_vps_key'
    if not key_path.exists():
        print("Generating SSH key for VPS access...")
        run(f'ssh-keygen -t ed25519 -f {key_path} -N "" -C "gcp-vps"')
        print(f"Key generated: {key_path}")
    return key_path

def provision_vps(ip, user='root', ssh_key=None, provider='generic'):
    """Provision a new VPS with GCP"""
    print(f"Provisioning VPS at {ip}...")
    print(f"Provider: {provider}")
    print()
    
    # Generate SSH key if needed
    key_path = generate_ssh_key()
    pub_key = f"{key_path}.pub"
    
    # Copy SSH key to VPS
    print("[1/3] Setting up SSH access...")
    if ssh_key:
        run(f'ssh-copy-id -i {ssh_key} {user}@{ip}')
    else:
        # Try password auth first, then key
        run(f'ssh-copy-id -i {pub_key} {user}@{ip}')
    
    # Upload and run bootstrap script
    print("[2/3] Uploading bootstrap script...")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write(BOOTSTRAP_SCRIPT)
        bootstrap_path = f.name
    
    run(f'scp -i {key_path} {bootstrap_path} {user}@{ip}:/tmp/gcp-bootstrap.sh')
    run(f'ssh -i {key_path} {user}@{ip} "chmod +x /tmp/gcp-bootstrap.sh && /tmp/gcp-bootstrap.sh"')
    
    # Clean up
    Path(bootstrap_path).unlink(missing_ok=True)
    
    print("[3/3] Adding to local mesh...")
    node_name = input("Name for this node (e.g., 'vps-hetzner'): ").strip()
    if node_name:
        run(f'gcp mesh-sync add {node_name} {ip} --user ghost', check=False)
    
    print()
    print("=== VPS Provisioned ===")
    print(f"IP: {ip}")
    print(f"User: ghost")
    print(f"SSH: ssh -i {key_path} ghost@{ip}")
    print()
    print("Next steps:")
    print("  1. Test: gcp mesh-sync status")
    print("  2. Sync: gcp mesh-sync sync 'status' --target {node_name}")
    print("  3. Backup target: configure in gcp backup")

def test_connection(ip, user='ghost', ssh_key=None):
    """Test SSH connection to VPS"""
    key_path = ssh_key or Path.home() / '.ssh' / 'gcp_vps_key'
    result = subprocess.run(
        ['ssh', '-i', str(key_path), '-o', 'ConnectTimeout=5', 
         '-o', 'BatchMode=yes', f'{user}@{ip}', 'echo', 'ok'],
        capture_output=True
    )
    return result.returncode == 0

def main():
    parser = argparse.ArgumentParser(description='Provision VPS with Ghost Control Plane')
    parser.add_argument('ip', help='VPS IP address')
    parser.add_argument('--user', default='root', help='Initial SSH user (default: root)')
    parser.add_argument('--ssh-key', help='Path to SSH private key')
    parser.add_argument('--provider', default='generic', 
                       choices=['generic', 'hetzner', 'vultr', 'digitalocean', 'linode'],
                       help='VPS provider (for provider-specific tweaks)')
    parser.add_argument('--test', action='store_true', help='Test connection only')
    
    args = parser.parse_args()
    
    if args.test:
        if test_connection(args.ip, args.user, args.ssh_key):
            print(f"Connection to {args.ip} successful")
        else:
            print(f"Cannot connect to {args.ip}")
            sys.exit(1)
    else:
        provision_vps(args.ip, args.user, args.ssh_key, args.provider)

if __name__ == '__main__':
    main()
