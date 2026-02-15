#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parent.parent
BASE = HOME / '.local' / 'share' / 'ghost-control-plane'

def run(cmd, cwd=None):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()

def get_latest_commit():
    rc, out, _ = run(['git', 'rev-parse', 'HEAD'], cwd=ROOT)
    return out if rc == 0 else None

def get_remote_commit():
    rc, out, _ = run(['git', 'ls-remote', 'origin', 'HEAD'], cwd=ROOT)
    if rc == 0:
        return out.split()[0] if out else None
    return None

def status():
    local = get_latest_commit()
    remote = get_remote_commit()
    
    print(f'local:  {local[:12] if local else "unknown"}')
    print(f'remote: {remote[:12] if remote else "unknown"}')
    
    if not local or not remote:
        print('status: error checking versions')
        return 1
    
    if local == remote:
        print('status: up to date')
        return 0
    else:
        print('status: update available')
        return 1

def update():
    print('== GCP Self-Update ==')
    
    # Check for updates
    local = get_latest_commit()
    remote = get_remote_commit()
    
    if not local or not remote:
        print('error: cannot check versions')
        return 1
    
    if local == remote:
        print('already up to date')
        return 0
    
    print(f'update available: {local[:12]} -> {remote[:12]}')
    
    # Pre-update checkpoint
    print('\n[1/4] Creating checkpoint...')
    checkpoint = BASE / 'checkpoints' / f'{datetime.now():%Y%m%d-%H%M%S}-pre-update.json'
    rc, out, _ = run(['python', str(ROOT / 'scripts' / 'gcp_checkpoint.py'), 'create', '--label', 'pre-update'])
    if rc != 0:
        print('checkpoint failed, aborting')
        return 1
    print(f'checkpoint: {checkpoint}')
    
    # Backup current state
    print('\n[2/4] Running backup...')
    rc, out, _ = run(['python', str(ROOT / 'scripts' / 'gcp_backup.py'), 'run', '--apply'])
    if rc != 0:
        print('backup failed, aborting')
        return 1
    print('backup complete')
    
    # Pull update
    print('\n[3/4] Pulling updates...')
    rc, out, err = run(['git', 'pull', 'origin', 'master'], cwd=ROOT)
    if rc != 0:
        print(f'git pull failed: {err}')
        print('attempting rollback...')
        # Could restore from checkpoint here
        return 1
    print(out)
    
    # Verify installation
    print('\n[4/4] Verifying installation...')
    rc, out, _ = run(['python', str(ROOT / 'scripts' / 'gcp_test.py')])
    if rc != 0:
        print('tests failed after update')
        print('consider: gcp checkpoint rollback')
        return 1
    
    print('\nupdate complete and verified')
    return 0

def check():
    rc = status()
    if rc != 0:
        print('\nrun "gcp update" to apply')
    return rc

parser = argparse.ArgumentParser(description='GCP self-updater')
sub = parser.add_subparsers(dest='cmd')
sub.add_parser('status', help='check update status')
sub.add_parser('check', help='check and notify if update available')
sub.add_parser('update', help='backup, update, and verify')
args = parser.parse_args()

if args.cmd == 'status':
    sys.exit(status())
elif args.cmd == 'check':
    sys.exit(check())
elif args.cmd == 'update':
    sys.exit(update())
else:
    parser.print_help()
    sys.exit(1)
