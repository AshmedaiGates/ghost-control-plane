#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG_REPO = ROOT / 'config' / 'backup.json'
CFG_USER = Path.home() / '.config' / 'ghost-control-plane' / 'backup.json'

DEFAULT_HOST = '67.217.61.166'
DEFAULT_USER = 'ghost'
DEFAULT_KEY = str(Path.home() / '.ssh' / 'gcp_vps_key')
DEFAULT_REMOTE_DIR = '/home/ghost/Backups/ghost-control-plane'


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def load_cfg():
    cfg = json.loads(CFG_REPO.read_text())
    if CFG_USER.exists():
        user = json.loads(CFG_USER.read_text())
        cfg.update(user)
    return cfg


def push(host, user, key, remote_dir, apply=False):
    cfg = load_cfg()
    src = Path(cfg['destinationDir']).expanduser()
    if not src.exists():
        raise SystemExit(f'local backup dir missing: {src}')

    ssh = f'ssh -i {key} -o BatchMode=yes -o ConnectTimeout=8'
    check_cmd = ['bash', '-lc', f'{ssh} {user}@{host} "mkdir -p {remote_dir}"']
    rc, out, err = run(check_cmd)
    if rc != 0:
        raise SystemExit(f'remote mkdir failed: {err or out}')

    rsync_cmd = [
        'rsync', '-az', '--delete', '--info=stats2,progress2',
        '-e', f'ssh -i {key} -o BatchMode=yes -o ConnectTimeout=8',
        f'{src}/', f'{user}@{host}:{remote_dir}/'
    ]

    print(f'local={src}')
    print(f'remote={user}@{host}:{remote_dir}')
    if not apply:
        print('mode=dry-run')
        print('cmd=' + ' '.join(rsync_cmd))
        return

    rc, out, err = run(rsync_cmd)
    if out:
        print(out)
    if rc != 0:
        raise SystemExit(f'rsync failed: {err}')
    print('push=ok')


parser = argparse.ArgumentParser(description='Push local encrypted backups to VPS target')
parser.add_argument('--apply', action='store_true')
parser.add_argument('--host', default=DEFAULT_HOST)
parser.add_argument('--user', default=DEFAULT_USER)
parser.add_argument('--key', default=DEFAULT_KEY)
parser.add_argument('--remote-dir', default=DEFAULT_REMOTE_DIR)
args = parser.parse_args()

push(args.host, args.user, args.key, args.remote_dir, apply=args.apply)
