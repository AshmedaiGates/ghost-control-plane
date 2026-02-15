#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path

DEFAULT_HOST = '67.217.61.166'
DEFAULT_USER = 'ghost'
DEFAULT_KEY = str(Path.home() / '.ssh' / 'gcp_vps_key')


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def remote_gcp(host, user, key, gcp_args):
    remote = f'cd ~/.openclaw/workspace/ghost-control-plane; ~/.local/bin/gcp {' '.join(gcp_args)}'
    cmd = ['ssh', '-i', key, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', f'{user}@{host}', 'bash', '-lc', remote]
    return run(cmd)


parser = argparse.ArgumentParser(description='Run CI on VPS node')
sub = parser.add_subparsers(dest='cmd')

p = sub.add_parser('run')
p.add_argument('name', default='ghost-control-plane')
p.add_argument('--host', default=DEFAULT_HOST)
p.add_argument('--user', default=DEFAULT_USER)
p.add_argument('--key', default=DEFAULT_KEY)

p = sub.add_parser('list')
p.add_argument('--host', default=DEFAULT_HOST)
p.add_argument('--user', default=DEFAULT_USER)
p.add_argument('--key', default=DEFAULT_KEY)

args = parser.parse_args()

if args.cmd == 'list':
    rc, out, err = remote_gcp(args.host, args.user, args.key, ['ci', 'list'])
elif args.cmd == 'run':
    rc, out, err = remote_gcp(args.host, args.user, args.key, ['ci', 'run', args.name])
else:
    parser.print_help()
    raise SystemExit(1)

if out:
    print(out)
if rc != 0:
    raise SystemExit(err or rc)
