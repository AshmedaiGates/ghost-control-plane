#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / 'state'
STATE.mkdir(parents=True, exist_ok=True)
MANIFEST = STATE / 'manifest.json'
UNITS_DIR = STATE / 'systemd-user'
UNITS_DIR.mkdir(parents=True, exist_ok=True)

USER_UNITS = [
    'gcp-snapshot.service', 'gcp-snapshot.timer',
    'gcp-autopilot.service', 'gcp-autopilot.timer',
    'gcp-selfheal.service', 'gcp-selfheal.timer',
    'gcp-soc-report.service', 'gcp-soc-report.timer',
    'gcp-mesh-ops.service', 'gcp-mesh-ops.timer',
    'gcp-backup.service', 'gcp-backup.timer',
]

CFG_USER = Path.home() / '.config' / 'systemd' / 'user'


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def sha256(path: Path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def pp_cmd(args):
    if Path('/usr/bin/powerprofilesctl').exists() and Path('/usr/bin/python').exists():
        return ['/usr/bin/python', '/usr/bin/powerprofilesctl'] + args
    return ['powerprofilesctl'] + args


def export_manifest():
    rc, out, _ = run(pp_cmd(['get']))
    power = out if rc == 0 else None

    timers = {}
    units = {}
    for unit in USER_UNITS:
        upath = CFG_USER / unit
        timers[unit] = {}
        if unit.endswith('.timer'):
            rc1, en, _ = run(['systemctl', '--user', 'is-enabled', unit])
            rc2, ac, _ = run(['systemctl', '--user', 'is-active', unit])
            timers[unit] = {
                'enabled': en if rc1 == 0 else 'disabled',
                'active': ac if rc2 == 0 else 'inactive',
            }
        if upath.exists():
            target = UNITS_DIR / unit
            target.write_text(upath.read_text())
            units[unit] = {
                'present': True,
                'sha256': sha256(target),
                'source': str(target),
            }
        else:
            units[unit] = {'present': False}

    manifest = {
        'version': 1,
        'generated_at': datetime.now().isoformat(),
        'power_profile': power,
        'timers': timers,
        'units': units,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(f'exported={MANIFEST}')


def load_manifest(path=None):
    p = Path(path) if path else MANIFEST
    if not p.exists():
        raise SystemExit(f'manifest missing: {p}')
    return json.loads(p.read_text())


def apply_manifest(path=None, apply=False):
    m = load_manifest(path)
    print(f'manifest={path or MANIFEST}')

    # Unit sync plan
    for unit, meta in m.get('units', {}).items():
        src = UNITS_DIR / unit
        dst = CFG_USER / unit
        if meta.get('present') and src.exists():
            need = (not dst.exists()) or (dst.read_text() != src.read_text())
            if need:
                print(f'plan: sync unit {unit}')
                if apply:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_text(src.read_text())
        elif not meta.get('present') and dst.exists():
            print(f'plan: keep existing extra unit {unit} (no deletion)')

    if apply:
        run(['systemctl', '--user', 'daemon-reload'])

    # Timer states
    for unit, st in m.get('timers', {}).items():
        if not unit.endswith('.timer'):
            continue
        want_en = st.get('enabled') == 'enabled'
        want_ac = st.get('active') == 'active'
        print(f'plan: {unit} enabled={want_en} active={want_ac}')
        if apply:
            run(['systemctl', '--user', 'enable' if want_en else 'disable', unit])
            run(['systemctl', '--user', 'start' if want_ac else 'stop', unit])

    # Power profile
    pp = m.get('power_profile')
    if pp:
        print(f'plan: power_profile={pp}')
        if apply:
            run(pp_cmd(['set', pp]))

    print('mode=' + ('apply' if apply else 'dry-run'))


parser = argparse.ArgumentParser(description='Ghost reproducible state export/apply (safe)')
parser.add_argument('--export', action='store_true', help='export current state manifest')
parser.add_argument('--apply', action='store_true', help='apply manifest')
parser.add_argument('--dry-run', action='store_true', help='show apply plan only')
parser.add_argument('--manifest', help='manifest path (default state/manifest.json)')
args = parser.parse_args()

if args.export:
    export_manifest()
elif args.apply or args.dry_run:
    apply_manifest(path=args.manifest, apply=(args.apply and not args.dry_run))
else:
    parser.print_help()
