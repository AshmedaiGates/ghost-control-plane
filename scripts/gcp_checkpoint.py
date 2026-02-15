#!/usr/bin/env python3
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path.home() / '.local' / 'share' / 'ghost-control-plane'
CHK = BASE / 'checkpoints'
BASE.mkdir(parents=True, exist_ok=True)
CHK.mkdir(parents=True, exist_ok=True)

TIMERS = ['gcp-snapshot.timer', 'gcp-autopilot.timer', 'gcp-selfheal.timer', 'gcp-soc-report.timer', 'gcp-mesh-ops.timer', 'gcp-backup.timer']


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def pp_cmd(args):
    if Path('/usr/bin/powerprofilesctl').exists() and Path('/usr/bin/python').exists():
        return ['/usr/bin/python', '/usr/bin/powerprofilesctl'] + args
    return ['powerprofilesctl'] + args


def timer_state(name):
    rc1, en, _ = run(['systemctl', '--user', 'is-enabled', name])
    rc2, ac, _ = run(['systemctl', '--user', 'is-active', name])
    return {
        'enabled': en if rc1 == 0 else 'disabled',
        'active': ac if rc2 == 0 else 'inactive',
    }


def create_checkpoint(label='manual'):
    rc, pp, _ = run(pp_cmd(['get']))
    data = {
        'created_at': datetime.now().isoformat(),
        'label': label,
        'power_profile': pp if rc == 0 else None,
        'timers': {name: timer_state(name) for name in TIMERS},
    }
    name = datetime.now().strftime('%Y%m%d-%H%M%S') + f'-{label}.json'
    path = CHK / name
    path.write_text(json.dumps(data, indent=2))
    print(path)


def list_checkpoints():
    files = sorted(CHK.glob('*.json'))
    if not files:
        print('No checkpoints found')
        return
    for f in files:
        print(f)


def restore_checkpoint(path):
    p = Path(path)
    if not p.exists():
        raise SystemExit(f'checkpoint not found: {p}')
    data = json.loads(p.read_text())

    pp = data.get('power_profile')
    if pp:
        rc, _, err = run(pp_cmd(['set', pp]))
        print(f'power_profile -> {pp} rc={rc}')
        if err:
            print(err)

    timers = data.get('timers', {})
    for name, st in timers.items():
        if st.get('enabled') == 'enabled':
            run(['systemctl', '--user', 'enable', name])
        else:
            run(['systemctl', '--user', 'disable', name])

        if st.get('active') == 'active':
            run(['systemctl', '--user', 'start', name])
        else:
            run(['systemctl', '--user', 'stop', name])

        rc1, en, _ = run(['systemctl', '--user', 'is-enabled', name])
        rc2, ac, _ = run(['systemctl', '--user', 'is-active', name])
        print(f'{name}: enabled={en if rc1 == 0 else "disabled"} active={ac if rc2 == 0 else "inactive"}')


parser = argparse.ArgumentParser(description='Ghost checkpoints (safe rollback metadata)')
parser.add_argument('--create', action='store_true')
parser.add_argument('--label', default='manual')
parser.add_argument('--list', action='store_true')
parser.add_argument('--restore')
args = parser.parse_args()

if args.list:
    list_checkpoints()
elif args.create:
    create_checkpoint(args.label)
elif args.restore:
    restore_checkpoint(args.restore)
else:
    parser.print_help()
