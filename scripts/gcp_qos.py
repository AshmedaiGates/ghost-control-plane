#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / 'state'
STATE.mkdir(parents=True, exist_ok=True)
LAST = STATE / 'network-qos-last.json'


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def get_default_interface():
    rc, out, _ = run(['ip', 'route', 'show', 'default'])
    if rc != 0 or not out:
        return None
    for ln in out.splitlines():
        if 'dev' in ln:
            parts = ln.split()
            for i, p in enumerate(parts):
                if p == 'dev' and i + 1 < len(parts):
                    return parts[i + 1]
    return None


def save_last(iface, mode):
    import json
    LAST.write_text(json.dumps({'iface': iface, 'mode': mode}, indent=2))


def load_last():
    import json
    if not LAST.exists():
        return None
    return json.loads(LAST.read_text())


def get_current_qdisc(iface):
    rc, out, _ = run(['tc', 'qdisc', 'show', 'dev', iface])
    return out if rc == 0 else ''


def apply_qos(iface, profile, apply=False):
    # fq_codel tuning profiles
    profiles = {
        'default': {
            'target': '5ms',
            'interval': '100ms',
            'quantum': '1514',
            'flows': '1024',
            'limit': '10240',
        },
        'gaming': {
            'target': '3ms',
            'interval': '50ms',
            'quantum': '1514',
            'flows': '2048',
            'limit': '8192',
        },
        'streaming': {
            'target': '4ms',
            'interval': '80ms',
            'quantum': '1514',
            'flows': '1024',
            'limit': '12288',
        },
    }

    p = profiles.get(profile, profiles['default'])
    current = get_current_qdisc(iface)

    print(f'iface={iface}')
    print(f'profile={profile}')
    print(f'current_qdisc={current[:200]}')
    print(f'target={p["target"]} interval={p["interval"]} quantum={p["quantum"]} flows={p["flows"]} limit={p["limit"]}')

    if not apply:
        print('mode=dry-run')
        return

    # Delete existing qdisc and add tuned fq_codel
    run(['sudo', '-n', 'tc', 'qdisc', 'del', 'dev', iface, 'root'])

    cmd = [
        'sudo', '-n', 'tc', 'qdisc', 'add', 'dev', iface, 'root', 'fq_codel',
        'target', p['target'],
        'interval', p['interval'],
        'quantum', p['quantum'],
        'flows', p['flows'],
        'limit', p['limit'],
        'ecn',
    ]
    rc, out, err = run(cmd)
    print(f'rc={rc}')
    if out:
        print(out)
    if err:
        print(err)

    if rc == 0:
        save_last(iface, profile)
        print(f'saved_last={LAST}')


def rollback(apply=False):
    last = load_last()
    if not last:
        raise SystemExit('no rollback state')
    iface = last.get('iface')
    mode = last.get('mode', 'default')
    print(f'rollback_to={mode} on {iface}')
    if apply:
        apply_qos(iface, mode, apply=True)


parser = argparse.ArgumentParser(description='Network QoS tuning (fq_codel)')
sub = parser.add_subparsers(dest='cmd')
sub.add_parser('status')
p = sub.add_parser('apply')
p.add_argument('profile', choices=['default', 'gaming', 'streaming'])
p.add_argument('--apply', action='store_true')
p.add_argument('--iface')
sub.add_parser('rollback')
args = parser.parse_args()

if args.cmd == 'status':
    iface = get_default_interface()
    print(f'default_iface={iface}')
    if iface:
        print(get_current_qdisc(iface))
    last = load_last()
    print(f'last_profile={last}')
elif args.cmd == 'apply':
    iface = args.iface or get_default_interface()
    if not iface:
        raise SystemExit('no default interface found')
    apply_qos(iface, args.profile, apply=args.apply)
elif args.cmd == 'rollback':
    rollback(apply=True)
else:
    parser.print_help()
