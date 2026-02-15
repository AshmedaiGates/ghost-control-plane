#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / 'gcp_profile.py'

SCENES = {
    'game': {
        'profile': 'performance',
        'verify': 20,
        'audio': 'lowlatency',
        'network': 'latency',
    },
    'code': {
        'profile': 'performance',
        'verify': 15,
        'audio': 'balanced',
        'network': 'latency',
    },
    'focus': {
        'profile': 'balanced',
        'verify': 15,
        'audio': 'balanced',
        'network': 'latency',
    },
    'travel': {
        'profile': 'battery',
        'verify': 20,
        'audio': 'powersave',
        'network': 'isp-auto',
    },
    'stream': {
        'profile': 'balanced',
        'verify': 20,
        'audio': 'lowlatency',
        'network': 'latency',
    },
}


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


parser = argparse.ArgumentParser(description='Ghost scene switcher (safe)')
parser.add_argument('--list', action='store_true', help='list scenes')
parser.add_argument('--scene', choices=sorted(SCENES.keys()))
parser.add_argument('--apply', action='store_true', help='apply scene now')
parser.add_argument('--dry-run', action='store_true', help='show planned command only')
args = parser.parse_args()

if args.list:
    print('Scenes: ' + ', '.join(sorted(SCENES.keys())))
    raise SystemExit(0)

if not args.scene:
    parser.error('--scene is required unless --list is used')

s = SCENES[args.scene]
cmd = [
    'python', str(PROFILE),
    '--profile', s['profile'],
    '--verify-seconds', str(s['verify']),
]
mode = 'dry-run'
if args.apply and not args.dry_run:
    cmd.append('--apply')
    mode = 'apply'
else:
    cmd.append('--dry-run')

print(f"Scene: {args.scene} ({mode})")
print('Power plan: ' + ' '.join(cmd))
print(f"Audio plan: python {ROOT / 'gcp_audio.py'} profile {s['audio']} {'--apply' if mode == 'apply' else ''}".strip())
print(f"Network plan: python {ROOT / 'gcp_network.py'} profile {s['network']} {'--apply' if mode == 'apply' else ''}".strip())

if mode == 'apply':
    # 1) power profile with safety checks/rollback
    rc, out, err = run(cmd)
    if out:
        print(out)
    if err:
        print(err)
    if rc != 0:
        raise SystemExit(rc)

    # 2) audio profile (safe runtime)
    a_cmd = ['python', str(ROOT / 'gcp_audio.py'), 'profile', s['audio'], '--apply']
    rc, out, err = run(a_cmd)
    if out:
        print(out)
    if err:
        print(err)
    if rc != 0:
        raise SystemExit(rc)

    # 3) network profile (reversible)
    n_cmd = ['python', str(ROOT / 'gcp_network.py'), 'profile', s['network'], '--apply']
    rc, out, err = run(n_cmd)
    if out:
        print(out)
    if err:
        print(err)
    if rc != 0:
        raise SystemExit(rc)
