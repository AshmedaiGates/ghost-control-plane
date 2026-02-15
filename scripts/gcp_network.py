#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / 'state'
STATE.mkdir(parents=True, exist_ok=True)
LAST = STATE / 'network-last.json'

DNS_PROFILES = {
    'isp-auto': {
        'ipv4.ignore-auto-dns': 'no',
        'ipv4.dns': '',
        'ipv6.ignore-auto-dns': 'no',
        'ipv6.dns': '',
    },
    'latency': {
        'ipv4.ignore-auto-dns': 'yes',
        'ipv4.dns': '1.1.1.1 1.0.0.1 9.9.9.9',
        'ipv6.ignore-auto-dns': 'yes',
        'ipv6.dns': '2606:4700:4700::1111 2606:4700:4700::1001 2620:fe::9',
    },
    'privacy': {
        'ipv4.ignore-auto-dns': 'yes',
        'ipv4.dns': '9.9.9.9 149.112.112.112',
        'ipv6.ignore-auto-dns': 'yes',
        'ipv6.dns': '2620:fe::9 2620:fe::fe',
    },
}


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def active_wifi_connection():
    rc, out, err = run(['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show', '--active'])
    if rc != 0:
        raise SystemExit(err or out)
    for ln in out.splitlines():
        parts = ln.split(':')
        if len(parts) >= 3 and parts[1] == '802-11-wireless' and parts[2]:
            return parts[0], parts[2]
    # fallback any active non-loopback
    for ln in out.splitlines():
        parts = ln.split(':')
        if len(parts) >= 3 and parts[1] != 'loopback' and parts[2]:
            return parts[0], parts[2]
    return None, None


def get_fields(conn):
    rc, out, err = run(['nmcli', '-t', '-f', 'ipv4.dns,ipv4.ignore-auto-dns,ipv6.dns,ipv6.ignore-auto-dns', 'connection', 'show', conn])
    if rc != 0:
        raise SystemExit(err or out)
    vals = {}
    for ln in out.splitlines():
        if ':' not in ln:
            continue
        k, v = ln.split(':', 1)
        vals[k.strip()] = v.strip()
    return {
        'ipv4.dns': vals.get('ipv4.dns', ''),
        'ipv4.ignore-auto-dns': vals.get('ipv4.ignore-auto-dns', 'no') or 'no',
        'ipv6.dns': vals.get('ipv6.dns', ''),
        'ipv6.ignore-auto-dns': vals.get('ipv6.ignore-auto-dns', 'no') or 'no',
    }


def show_status():
    conn, dev = active_wifi_connection()
    print(f'active_connection={conn} device={dev}')
    if not conn:
        return
    f = get_fields(conn)
    print('dns_state=' + json.dumps(f))
    rc, out, _ = run(['resolvectl', 'status'])
    if rc == 0:
        for ln in out.splitlines():
            if ('Current DNS Server' in ln) or ('DNS Servers' in ln and 'Fallback' not in ln) or (f'Link' in ln and dev in ln):
                print(ln)


def apply_profile(name, apply=False):
    conn, dev = active_wifi_connection()
    print(f'active_connection={conn} device={dev}')
    if not conn:
        raise SystemExit('no active non-loopback connection')
    target = DNS_PROFILES[name]
    current = get_fields(conn)
    print('current=' + json.dumps(current))
    print('target=' + json.dumps(target))
    if not apply:
        print('mode=dry-run')
        return

    LAST.write_text(json.dumps({'connection': conn, 'device': dev, 'state': current}, indent=2))

    for k, v in target.items():
        rc, out, err = run(['nmcli', 'connection', 'modify', conn, k, v])
        print(f'modify {k}={v!r} rc={rc}')
        if out:
            print(out)
        if err:
            print(err)
        if rc != 0:
            raise SystemExit(rc)

    rc, out, err = run(['nmcli', 'connection', 'up', conn])
    print(f'connection up rc={rc}')
    if out:
        print(out)
    if err:
        print(err)
    if rc != 0:
        raise SystemExit(rc)

    print(f'saved_last={LAST}')
    show_status()


def rollback(apply=False):
    if not LAST.exists():
        raise SystemExit(f'no rollback state found: {LAST}')
    saved = json.loads(LAST.read_text())
    conn = saved['connection']
    st = saved['state']
    print(f'rollback_connection={conn}')
    print('rollback_state=' + json.dumps(st))
    if not apply:
        print('mode=dry-run')
        return
    for k in ('ipv4.dns', 'ipv4.ignore-auto-dns', 'ipv6.dns', 'ipv6.ignore-auto-dns'):
        rc, out, err = run(['nmcli', 'connection', 'modify', conn, k, st.get(k, '')])
        print(f'modify {k} rc={rc}')
        if out:
            print(out)
        if err:
            print(err)
    rc, out, err = run(['nmcli', 'connection', 'up', conn])
    print(f'connection up rc={rc}')
    if out:
        print(out)
    if err:
        print(err)
    show_status()


parser = argparse.ArgumentParser(description='Network DNS profile manager (safe-ish, reversible)')
sub = parser.add_subparsers(dest='cmd')
sub.add_parser('status')
p = sub.add_parser('profile')
p.add_argument('name', choices=sorted(DNS_PROFILES.keys()))
p.add_argument('--apply', action='store_true')
r = sub.add_parser('rollback')
r.add_argument('--apply', action='store_true')
args = parser.parse_args()

if args.cmd == 'status':
    show_status()
elif args.cmd == 'profile':
    apply_profile(args.name, apply=args.apply)
elif args.cmd == 'rollback':
    rollback(apply=args.apply)
else:
    parser.print_help()
