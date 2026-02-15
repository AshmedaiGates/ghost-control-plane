#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / 'state'
STATE.mkdir(parents=True, exist_ok=True)
LAST = STATE / 'audio-last.json'

PROFILES = {
    'balanced': {'quantum': '0', 'rate': '0'},
    'lowlatency': {'quantum': '128', 'rate': '48000'},
    'studio': {'quantum': '64', 'rate': '48000'},
    'powersave': {'quantum': '1024', 'rate': '48000'},
}


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def parse_settings(raw):
    out = {}
    for ln in raw.splitlines():
        m = re.search(r"key:'([^']+)'\s+value:'([^']*)'", ln)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def read_audio_state():
    rc, out, err = run(['pw-metadata', '-n', 'settings'])
    if rc != 0:
        raise SystemExit(f'pw-metadata failed: {err or out}')
    s = parse_settings(out)
    return {
        'clock.force-quantum': s.get('clock.force-quantum', '0'),
        'clock.force-rate': s.get('clock.force-rate', '0'),
        'clock.quantum': s.get('clock.quantum'),
        'clock.rate': s.get('clock.rate'),
    }


def write_setting(key, val):
    rc, out, err = run(['pw-metadata', '-n', 'settings', '0', key, str(val)])
    return rc, out, err


def save_last(state):
    LAST.write_text(json.dumps(state, indent=2))


def status():
    s = read_audio_state()
    print('audio_state=' + json.dumps(s))
    rc, out, _ = run(['wpctl', 'status'])
    if rc == 0:
        for ln in out.splitlines():
            if 'Sinks:' in ln or 'Sources:' in ln or 'Audio' in ln or ' * ' in ln:
                print(ln)


def apply_profile(profile, apply=False):
    target = PROFILES[profile]
    current = read_audio_state()
    print(f'profile={profile}')
    print('current=' + json.dumps(current))
    print('target=' + json.dumps(target))

    if not apply:
        print('mode=dry-run')
        return

    save_last(current)
    for k, v in [('clock.force-quantum', target['quantum']), ('clock.force-rate', target['rate'])]:
        rc, out, err = write_setting(k, v)
        print(f'set {k}={v} rc={rc}')
        if out:
            print(out)
        if err:
            print(err)
        if rc != 0:
            raise SystemExit(rc)

    print(f'saved_last={LAST}')
    status()


def rollback(apply=False):
    if not LAST.exists():
        raise SystemExit(f'no rollback state found: {LAST}')
    prev = json.loads(LAST.read_text())
    print('rollback_target=' + json.dumps(prev))
    if not apply:
        print('mode=dry-run')
        return
    for k in ('clock.force-quantum', 'clock.force-rate'):
        v = prev.get(k, '0')
        rc, out, err = write_setting(k, v)
        print(f'set {k}={v} rc={rc}')
        if out:
            print(out)
        if err:
            print(err)
    status()


parser = argparse.ArgumentParser(description='Audio tuning profiles (safe runtime)')
sub = parser.add_subparsers(dest='cmd')
sub.add_parser('status')
p = sub.add_parser('profile')
p.add_argument('name', choices=sorted(PROFILES.keys()))
p.add_argument('--apply', action='store_true')
r = sub.add_parser('rollback')
r.add_argument('--apply', action='store_true')
args = parser.parse_args()

if args.cmd == 'status':
    status()
elif args.cmd == 'profile':
    apply_profile(args.name, apply=args.apply)
elif args.cmd == 'rollback':
    rollback(apply=args.apply)
else:
    parser.print_help()
