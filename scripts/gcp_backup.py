#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG_REPO = ROOT / 'config' / 'backup.json'
CFG_USER = Path.home() / '.config' / 'ghost-control-plane' / 'backup.json'
PASS_FILE = Path.home() / '.config' / 'ghost-control-plane' / 'backup-passphrase'


def run(cmd, **kwargs):
    p = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def load_cfg():
    cfg = json.loads(CFG_REPO.read_text())
    if CFG_USER.exists():
        user = json.loads(CFG_USER.read_text())
        cfg.update(user)
    return cfg


def get_passphrase():
    env = os.getenv('GCP_BACKUP_PASSPHRASE')
    if env:
        return env
    if PASS_FILE.exists():
        return PASS_FILE.read_text().strip()
    return None


def ensure_passphrase():
    if PASS_FILE.exists():
        return PASS_FILE
    PASS_FILE.parent.mkdir(parents=True, exist_ok=True)
    rc, out, err = run(['bash', '-lc', 'openssl rand -base64 48'])
    if rc != 0 or not out:
        raise SystemExit(f'failed to generate passphrase: {err or out}')
    PASS_FILE.write_text(out.strip() + '\n')
    os.chmod(PASS_FILE, 0o600)
    return PASS_FILE


def existing_sources(cfg):
    out = []
    for s in cfg.get('sources', []):
        p = Path(s).expanduser()
        if p.exists():
            out.append(p)
    return out


def latest_backup(dest):
    files = sorted(dest.glob('*.tar.zst.gpg'))
    return files[-1] if files else None


def backup_status(cfg):
    dest = Path(cfg['destinationDir']).expanduser()
    src = existing_sources(cfg)
    print(f'destination={dest}')
    print(f'sources={len(src)}')
    for s in src:
        print(f' - {s}')
    print(f'passphrase_file={PASS_FILE} exists={PASS_FILE.exists()}')
    lb = latest_backup(dest) if dest.exists() else None
    print(f'latest_backup={lb}')


def prune(dest, keep_last):
    files = sorted(dest.glob('*.tar.zst.gpg'))
    if len(files) <= keep_last:
        return 0
    removed = 0
    for f in files[:-keep_last]:
        f.unlink(missing_ok=True)
        removed += 1
    return removed


def create_backup(cfg, apply=False):
    dest = Path(cfg['destinationDir']).expanduser()
    srcs = existing_sources(cfg)
    if not srcs:
        raise SystemExit('no valid sources to back up')

    print(f'destination={dest}')
    print(f'filesets={len(srcs)}')
    for s in srcs:
        print(f' - {s}')

    if not apply:
        print('mode=dry-run')
        return

    ensure_passphrase()
    pw = get_passphrase()
    if not pw:
        raise SystemExit('no backup passphrase available')

    dest.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    tmp = Path(tempfile.gettempdir()) / f'gcp-backup-{ts}.tar.zst'
    out = dest / f'gcp-backup-{ts}.tar.zst.gpg'

    tar_cmd = ['tar', '-cf', '-', *[str(p) for p in srcs]]
    zstd_cmd = ['zstd', '-T0', '-19', '-o', str(tmp)]

    p1 = subprocess.Popen(tar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
    p2 = subprocess.Popen(zstd_cmd, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
    p1.stdout.close()
    _, err2 = p2.communicate()
    _, err1 = p1.communicate()
    if p1.returncode != 0 or p2.returncode != 0:
        raise SystemExit(f'tar/zstd failed: tar={p1.returncode} {err1.decode(errors="ignore")} zstd={p2.returncode} {err2.decode(errors="ignore")}')

    rc, so, se = run([
        'gpg', '--batch', '--yes', '--pinentry-mode', 'loopback',
        '--passphrase-fd', '0', '--symmetric', '--cipher-algo', 'AES256',
        '-o', str(out), str(tmp)
    ], input=pw)
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass

    if rc != 0:
        raise SystemExit(f'gpg encrypt failed: {se or so}')

    print(f'backup_created={out}')
    removed = prune(dest, int(cfg.get('retention', {}).get('keepLast', 14)))
    print(f'pruned={removed}')


def verify_latest(cfg):
    dest = Path(cfg['destinationDir']).expanduser()
    lb = latest_backup(dest)
    if not lb:
        raise SystemExit('no backup found')
    pw = get_passphrase()
    if not pw:
        raise SystemExit('no backup passphrase available')

    with tempfile.NamedTemporaryFile(suffix='.tar.zst', delete=False) as tf:
        temp = Path(tf.name)

    rc, so, se = run([
        'gpg', '--batch', '--yes', '--pinentry-mode', 'loopback', '--passphrase-fd', '0',
        '-o', str(temp), '-d', str(lb)
    ], input=pw)
    if rc != 0:
        temp.unlink(missing_ok=True)
        raise SystemExit(f'gpg decrypt failed: {se or so}')

    rc, so, se = run(['bash', '-lc', f'zstd -dc {shlex_quote(str(temp))} | tar -tf - | head -n 20'])
    temp.unlink(missing_ok=True)
    if rc != 0:
        raise SystemExit(f'archive verify failed: {se or so}')
    print(f'verified={lb}')
    print(so)


def shlex_quote(s):
    import shlex
    return shlex.quote(s)


parser = argparse.ArgumentParser(description='Encrypted backups (safe local/off-device-ready)')
sub = parser.add_subparsers(dest='cmd')
sub.add_parser('status')
r = sub.add_parser('run')
r.add_argument('--apply', action='store_true')
sub.add_parser('verify')
sub.add_parser('init-passphrase')
args = parser.parse_args()

cfg = load_cfg()
if args.cmd == 'status':
    backup_status(cfg)
elif args.cmd == 'run':
    create_backup(cfg, apply=args.apply)
elif args.cmd == 'verify':
    verify_latest(cfg)
elif args.cmd == 'init-passphrase':
    p = ensure_passphrase()
    print(f'passphrase_file={p}')
else:
    parser.print_help()
