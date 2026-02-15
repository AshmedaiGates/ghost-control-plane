#!/usr/bin/env python3
"""
Ghost Control Plane - Android Integration
Mobile interface for GCP via web dashboard and Termux
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
BASE = HOME / '.local' / 'share' / 'ghost-control-plane'
ANDROID_DIR = BASE / 'android'
ANDROID_DIR.mkdir(parents=True, exist_ok=True)

TERMUX_SETUP = '''
# Ghost Control Plane - Termux Setup
# Run this in Termux app on Android

pkg update
pkg install -y openssh git python

# Generate SSH key
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""

echo "=== Add this public key to your laptop/VPS ==="
cat ~/.ssh/id_ed25519.pub
echo

echo "=== Then connect with ==="
echo "ssh ghost@<your-ip>"
'''

WEB_DASHBOARD_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ghost Control</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 20px;
            max-width: 480px;
            margin: 0 auto;
        }
        h1 { color: #ff6b35; margin-bottom: 20px; font-size: 24px; }
        .card {
            background: #1a1a1a;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
            border: 1px solid #333;
        }
        .card h2 { font-size: 16px; color: #888; margin-bottom: 12px; text-transform: uppercase; }
        .btn {
            display: block;
            width: 100%;
            padding: 16px;
            margin-bottom: 8px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-primary { background: #ff6b35; color: white; }
        .btn-secondary { background: #333; color: #fff; }
        .btn-success { background: #28a745; color: white; }
        .btn-danger { background: #dc3545; color: white; }
        .btn:active { transform: scale(0.98); }
        .status { 
            padding: 12px; 
            border-radius: 8px; 
            background: #222;
            font-family: monospace;
            font-size: 12px;
            white-space: pre-wrap;
            max-height: 200px;
            overflow-y: auto;
        }
        .health-good { color: #28a745; }
        .health-bad { color: #dc3545; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    </style>
</head>
<body>
    <h1>🔥 Ghost Control</h1>
    
    <div class="card">
        <h2>Health Status</h2>
        <div id="health" class="status">Loading...</div>
    </div>
    
    <div class="card">
        <h2>Scenes</h2>
        <div class="grid">
            <button class="btn btn-primary" onclick="run('scene game --apply')">🎮 Game</button>
            <button class="btn btn-primary" onclick="run('scene code --apply')">💻 Code</button>
            <button class="btn btn-secondary" onclick="run('scene focus --apply')">🎯 Focus</button>
            <button class="btn btn-secondary" onclick="run('scene travel --apply')">✈️ Travel</button>
        </div>
    </div>
    
    <div class="card">
        <h2>Quick Actions</h2>
        <button class="btn btn-success" onclick="run('battle network-reset')">🌐 Fix Network</button>
        <button class="btn btn-success" onclick="run('battle emergency-perf')">⚡ Max Perf</button>
        <button class="btn btn-danger" onclick="run('backup run --apply')">💾 Backup Now</button>
        <button class="btn btn-secondary" onclick="run('dashboard')">📊 Dashboard</button>
    </div>
    
    <div class="card">
        <h2>Custom Command</h2>
        <input type="text" id="cmd" placeholder="gcp ..." style="width:100%;padding:12px;border-radius:8px;border:none;background:#222;color:#fff;margin-bottom:8px;">
        <button class="btn btn-primary" onclick="runCustom()">Run</button>
    </div>
    
    <div class="card">
        <h2>Output</h2>
        <div id="output" class="status">Ready</div>
    </div>

    <script>
        const API_BASE = ''; // Same origin
        
        async function run(cmd) {
            document.getElementById('output').textContent = 'Running: gcp ' + cmd + '...';
            try {
                const res = await fetch('/api/run', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({cmd})
                });
                const data = await res.json();
                document.getElementById('output').textContent = data.output || data.error || 'Done';
            } catch(e) {
                document.getElementById('output').textContent = 'Error: ' + e.message;
            }
        }
        
        function runCustom() {
            const cmd = document.getElementById('cmd').value;
            if (cmd) run(cmd);
        }
        
        async function loadHealth() {
            try {
                const res = await fetch('/api/health');
                const data = await res.json();
                document.getElementById('health').textContent = JSON.stringify(data, null, 2);
            } catch(e) {
                document.getElementById('health').textContent = 'Health check failed';
            }
        }
        
        // Load health on startup
        loadHealth();
        setInterval(loadHealth, 30000); // Refresh every 30s
    </script>
</body>
</html>
'''

def setup_termux():
    """Generate Termux setup instructions"""
    print("=== Android (Termux) Setup ===")
    print()
    print(TERMUX_SETUP)
    print()
    
    # Save to file
    termux_file = ANDROID_DIR / 'termux-setup.sh'
    termux_file.write_text(TERMUX_SETUP)
    print(f"Saved to: {termux_file}")

def setup_web_dashboard():
    """Setup web dashboard for mobile"""
    dashboard_file = ANDROID_DIR / 'mobile-dashboard.html'
    dashboard_file.write_text(WEB_DASHBOARD_HTML)
    print(f"Mobile dashboard saved to: {dashboard_file}")
    print()
    print("To serve it:")
    print(f"  cd {ANDROID_DIR}")
    print("  python3 -m http.server 8080")
    print("  # Open http://your-laptop-ip:8080/mobile-dashboard.html on phone")

def generate_tasker_xml():
    """Generate Tasker task definitions for scene switching"""
    tasks = {
        'gcp_game_scene': {
            'name': 'GCP Game Scene',
            'command': 'gcp scene game --apply',
        },
        'gcp_code_scene': {
            'name': 'GCP Code Scene',
            'command': 'gcp scene code --apply',
        },
        'gcp_focus_scene': {
            'name': 'GCP Focus Scene',
            'command': 'gcp scene focus --apply',
        },
        'gcp_network_reset': {
            'name': 'GCP Fix Network',
            'command': 'gcp battle network-reset',
        },
        'gcp_backup_now': {
            'name': 'GCP Backup Now',
            'command': 'gcp backup run --apply',
        },
    }
    
    # Tasker doesn't import XML easily, so provide instructions
    print("=== Tasker Setup ===")
    print()
    print("Create these tasks in Tasker:")
    for task_id, task in tasks.items():
        print(f"\n{task['name']}:")
        print(f"  Action: Code → Run Shell")
        print(f"  Command: ssh ghost@<your-ip> '{task['command']}'")
        print(f"  Check 'Run as root' if needed")
    print()
    print("Then create profiles to auto-trigger:")
    print("  - WiFi connected to home → Game scene")
    print("  - Bluetooth disconnected → Travel scene")
    print("  - Time 9 AM → Code scene")

def setup_ssh_from_phone():
    """Instructions for SSH from phone to control GCP"""
    print("=== SSH Control from Android ===")
    print()
    print("1. Install Termux from F-Droid (not Play Store)")
    print("2. In Termux:")
    print("   pkg install openssh")
    print("   ssh-keygen -t ed25519")
    print("   cat ~/.ssh/id_ed25519.pub")
    print()
    print("3. Add that key to your laptop/VPS:")
    print("   gcp android add-key <the-pub-key>")
    print()
    print("4. Then from Termux:")
    print("   ssh ghost@<ip>")
    print("   gcp status")
    print("   gcp scene game --apply")

def main():
    parser = argparse.ArgumentParser(description='Android integration for GCP')
    sub = parser.add_subparsers(dest='cmd')
    
    sub.add_parser('termux', help='setup Termux environment')
    sub.add_parser('dashboard', help='generate mobile web dashboard')
    sub.add_parser('tasker', help='Tasker automation setup')
    sub.add_parser('ssh', help='SSH control from phone')
    
    args = parser.parse_args()
    
    if args.cmd == 'termux':
        setup_termux()
    elif args.cmd == 'dashboard':
        setup_web_dashboard()
    elif args.cmd == 'tasker':
        generate_tasker_xml()
    elif args.cmd == 'ssh':
        setup_ssh_from_phone()
    else:
        print("Android integration options:")
        print()
        print("  gcp android termux      # Linux env on Android")
        print("  gcp android dashboard   # Web UI for phone")
        print("  gcp android tasker      # Automation app setup")
        print("  gcp android ssh         # SSH control")
        print()
        print(f"Config directory: {ANDROID_DIR}")

if __name__ == '__main__':
    main()
