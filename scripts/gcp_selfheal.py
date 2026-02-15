#!/usr/bin/env python3
import argparse
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = Path.home() / '.local' / 'share' / 'ghost-control-plane'
CFG_USER = Path.home() / '.config' / 'systemd' / 'user'

REQUIRED_DIRS = [BASE, BASE / 'snapshots', BASE / 'checkpoints']
TIMER_UNITS = ['gcp-snapshot.timer', 'gcp-autopilot.timer', 'gcp-selfheal.timer', 'gcp-soc-report.timer', 'gcp-mesh-ops.timer', 'gcp-backup.timer']
SCRIPT_GLOB = 'gcp_*.py'


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def is_exec(path: Path):
    return bool(path.stat().st_mode & stat.S_IXUSR)


def ensure_exec(path: Path):
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR)


def add_action(actions, kind, desc, fn):
    actions.append({'kind': kind, 'desc': desc, 'fn': fn})


def evaluate():
    actions = []

    for d in REQUIRED_DIRS:
        if not d.exists():
            add_action(actions, 'mkdir', f'Create {d}', lambda d=d: d.mkdir(parents=True, exist_ok=True))

    for s in ROOT.glob(SCRIPT_GLOB):
        if not is_exec(s):
            add_action(actions, 'chmod', f'Make executable: {s.name}', lambda s=s: ensure_exec(s))

    if not CFG_USER.exists():
        add_action(actions, 'mkdir', f'Create {CFG_USER}', lambda: CFG_USER.mkdir(parents=True, exist_ok=True))
    for unit in TIMER_UNITS + ['gcp-snapshot.service', 'gcp-autopilot.service', 'gcp-selfheal.service', 'gcp-soc-report.service', 'gcp-mesh-ops.service', 'gcp-backup.service']:
        dst = CFG_USER / unit
        src = ROOT.parent / 'systemd' / 'user' / unit
        if src.exists() and (not dst.exists() or dst.read_text() != src.read_text()):
            add_action(actions, 'sync-unit', f'Sync unit: {unit}', lambda src=src, dst=dst: dst.write_text(src.read_text()))

    # timer enable/start checks
    for t in TIMER_UNITS:
        rc_en, en, _ = run(['systemctl', '--user', 'is-enabled', t])
        rc_ac, ac, _ = run(['systemctl', '--user', 'is-active', t])
        if rc_en != 0 or en != 'enabled':
            add_action(actions, 'enable-timer', f'Enable timer: {t}', lambda t=t: run(['systemctl', '--user', 'enable', t]))
        if rc_ac != 0 or ac != 'active':
            add_action(actions, 'start-timer', f'Start timer: {t}', lambda t=t: run(['systemctl', '--user', 'start', t]))

    return actions


parser = argparse.ArgumentParser(description='Ghost safe self-healing (reversible)')
parser.add_argument('--apply', action='store_true', help='apply fixes')
parser.add_argument('--dry-run', action='store_true', help='show only (default)')
args = parser.parse_args()

actions = evaluate()
print(f'actions_found={len(actions)}')
for i, a in enumerate(actions, 1):
    print(f'{i}. [{a["kind"]}] {a["desc"]}')

mode = 'apply' if args.apply and not args.dry_run else 'dry-run'
print(f'mode={mode}')

if mode == 'apply':
    # Create a checkpoint before changes
    ck = ROOT / 'gcp_checkpoint.py'
    rc, out, err = run(['python', str(ck), '--create', '--label', 'selfheal'])
    print(f'checkpoint_rc={rc}')
    if out:
        print(f'checkpoint={out}')
    if err:
        print(err)

    # Reload user daemon once if any units changed
    if any(a['kind'] == 'sync-unit' for a in actions):
        run(['systemctl', '--user', 'daemon-reload'])

    for a in actions:
        try:
            r = a['fn']()
            if isinstance(r, tuple):
                rc = r[0]
                print(f'apply [{a["kind"]}] rc={rc} :: {a["desc"]}')
            else:
                print(f'apply [{a["kind"]}] ok :: {a["desc"]}')
        except Exception as e:
            print(f'apply [{a["kind"]}] error={e} :: {a["desc"]}')
