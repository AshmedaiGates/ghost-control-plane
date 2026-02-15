#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path.home() / '.local' / 'share' / 'ghost-control-plane' / 'soc'
SNAP = BASE / 'snapshots'
BASE.mkdir(parents=True, exist_ok=True)
SNAP.mkdir(parents=True, exist_ok=True)
BASELINE = BASE / 'baseline.json'

SVC_PATTERNS = ('ssh', 'sshd', 'docker', 'libvirtd', 'avahi', 'bluetooth', 'openclaw')


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def parse_ss_listeners(text):
    rows = []
    for ln in (text or '').splitlines()[1:]:
        parts = ln.split()
        if len(parts) < 5:
            continue
        proto = parts[0]
        local = parts[4]
        proc = ' '.join(parts[6:]) if len(parts) > 6 else ''
        rows.append({'proto': proto, 'local': local, 'proc': proc})
    return rows


def parse_ufw_rules(text):
    rules = []
    capture = False
    for ln in (text or '').splitlines():
        if ln.strip().startswith('To') and 'Action' in ln and 'From' in ln:
            capture = True
            continue
        if capture:
            s = ln.strip()
            if not s or s.startswith('--'):
                continue
            rules.append(s)
    return rules


def service_slice(text):
    out = []
    for ln in (text or '').splitlines():
        low = ln.lower()
        if any(p in low for p in SVC_PATTERNS):
            out.append(ln)
    return out


def package_updates():
    updates = {'pacman_updates': [], 'aur_updates': [], 'brew_updates': [], 'apt_updates': [], 'dnf_updates': []}

    if shutil.which('pacman'):
        rc, out, _ = run(['pacman', '-Qu'])
        updates['pacman_updates'] = [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []

    if shutil.which('paru'):
        rc, out, _ = run(['paru', '-Qua'])
        updates['aur_updates'] = [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []

    if shutil.which('brew'):
        rc, out, _ = run(['brew', 'outdated'])
        updates['brew_updates'] = [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []

    if shutil.which('apt'):
        # Read-only: simulate upgrade list
        rc, out, _ = run(['apt', 'list', '--upgradable'])
        if rc == 0:
            updates['apt_updates'] = [ln for ln in out.splitlines()[1:] if ln.strip()]

    if shutil.which('dnf'):
        rc, out, _ = run(['dnf', 'check-update'])
        # dnf returns 100 when updates are available
        if rc in (0, 100):
            updates['dnf_updates'] = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith('Last metadata')]

    return updates


def collect_snapshot():
    ts = datetime.now().isoformat()
    snap = {'ts': ts}

    rc, out, _ = run(['ss', '-ltnup'])
    snap['listeners'] = parse_ss_listeners(out) if rc == 0 else []

    rc, out, _ = run(['sudo', '-n', 'ufw', 'status', 'verbose'])
    snap['ufw_rules'] = parse_ufw_rules(out) if rc == 0 else []

    rc, out, _ = run(['systemctl', 'list-unit-files', '--type=service'])
    snap['services_interest'] = service_slice(out) if rc == 0 else []

    snap.update(package_updates())

    return snap


def save_snapshot(snap):
    name = datetime.now().strftime('%Y%m%d-%H%M%S') + '.json'
    path = SNAP / name
    path.write_text(json.dumps(snap, indent=2))
    return path


def load_latest():
    files = sorted(SNAP.glob('*.json'))
    if not files:
        return None, None
    p = files[-1]
    return p, json.loads(p.read_text())


def load_baseline():
    if not BASELINE.exists():
        return None
    return json.loads(BASELINE.read_text())


def set_baseline(source='latest'):
    if source == 'latest':
        p, snap = load_latest()
        if not snap:
            raise SystemExit('No snapshots found to set baseline')
    else:
        p = Path(source)
        if not p.exists():
            raise SystemExit(f'file not found: {p}')
        snap = json.loads(p.read_text())
    BASELINE.write_text(json.dumps(snap, indent=2))
    print(f'baseline_set={BASELINE}')


def as_set_listeners(snap):
    return {f"{x.get('proto')}|{x.get('local')}|{x.get('proc')}" for x in snap.get('listeners', [])}


def diff_report(base, cur):
    out = []
    sev = 'INFO'

    b_list = as_set_listeners(base)
    c_list = as_set_listeners(cur)
    new_listeners = sorted(c_list - b_list)
    gone_listeners = sorted(b_list - c_list)

    b_rules = set(base.get('ufw_rules', []))
    c_rules = set(cur.get('ufw_rules', []))
    new_rules = sorted(c_rules - b_rules)
    gone_rules = sorted(b_rules - c_rules)

    if new_listeners:
        sev = 'WARN'
        out.append('New listeners:')
        out.extend([f'  + {x}' for x in new_listeners])
    if gone_listeners:
        out.append('Removed listeners:')
        out.extend([f'  - {x}' for x in gone_listeners])

    if new_rules:
        sev = 'WARN'
        out.append('New firewall allow/rule lines:')
        out.extend([f'  + {x}' for x in new_rules])
    if gone_rules:
        out.append('Removed firewall rule lines:')
        out.extend([f'  - {x}' for x in gone_rules])

    # Package drift severity only if large
    p_total = (
        len(cur.get('pacman_updates', []))
        + len(cur.get('aur_updates', []))
        + len(cur.get('brew_updates', []))
        + len(cur.get('apt_updates', []))
        + len(cur.get('dnf_updates', []))
    )
    if p_total >= 20 and sev == 'INFO':
        sev = 'WARN'
    out.append(
        'Pending updates: '
        f'pacman={len(cur.get("pacman_updates", []))} '
        f'aur={len(cur.get("aur_updates", []))} '
        f'brew={len(cur.get("brew_updates", []))} '
        f'apt={len(cur.get("apt_updates", []))} '
        f'dnf={len(cur.get("dnf_updates", []))}'
    )

    if not new_listeners and not new_rules and not gone_listeners and not gone_rules:
        out.append('No network/firewall drift vs baseline.')

    return sev, out


parser = argparse.ArgumentParser(description='Ghost SOC drift intelligence (read-only)')
parser.add_argument('--snapshot', action='store_true', help='collect and save snapshot')
parser.add_argument('--baseline', choices=['set-latest', 'show'], help='baseline actions')
parser.add_argument('--baseline-file', help='set baseline from explicit snapshot file')
parser.add_argument('--diff', action='store_true', help='diff latest snapshot against baseline')
parser.add_argument('--report', action='store_true', help='snapshot + diff report')
args = parser.parse_args()

if args.snapshot or args.report:
    snap = collect_snapshot()
    p = save_snapshot(snap)
    print(f'snapshot={p}')

if args.baseline == 'set-latest':
    set_baseline('latest')
elif args.baseline_file:
    set_baseline(args.baseline_file)
elif args.baseline == 'show':
    if BASELINE.exists():
        print(BASELINE)
    else:
        print('baseline missing')

if args.diff or args.report:
    base = load_baseline()
    _, cur = load_latest()
    if not base:
        raise SystemExit('baseline missing (set with --baseline set-latest)')
    if not cur:
        raise SystemExit('no snapshots found')
    sev, lines = diff_report(base, cur)
    print(f'severity={sev}')
    for ln in lines:
        print(ln)
