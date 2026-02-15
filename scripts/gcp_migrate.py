#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path

HOME = Path.home()
BASE = HOME / '.local' / 'share' / 'ghost-control-plane'
MIGRATIONS_DIR = BASE / 'migrations'
MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

def run(cmd, cwd=None):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()

def get_distro():
    """Detect current distro"""
    if Path('/etc/os-release').exists():
        with open('/etc/os-release') as f:
            for ln in f:
                if ln.startswith('ID='):
                    return ln.split('=')[1].strip().strip('"')
    return 'unknown'

def get_packages():
    """Get list of installed packages"""
    distro = get_distro()
    packages = []
    
    if shutil.which('pacman'):
        rc, out, _ = run(['pacman', '-Qqe'])
        packages = out.splitlines() if rc == 0 else []
    elif shutil.which('apt'):
        rc, out, _ = run(['dpkg', '--get-selections'])
        if rc == 0:
            packages = [ln.split()[0] for ln in out.splitlines() if '\tinstall' in ln]
    elif shutil.which('dnf'):
        rc, out, _ = run(['dnf', 'list', 'installed'])
        packages = out.splitlines() if rc == 0 else []
    
    return packages

def get_dotfiles():
    """Get list of important dotfiles"""
    dotfiles = []
    for pattern in ['.config/*', '.bash*', '.zsh*', '.fish*', '.gitconfig', '.ssh/config', '.tmux.conf']:
        for p in HOME.glob(pattern):
            if p.is_file():
                dotfiles.append(str(p.relative_to(HOME)))
    return dotfiles

def get_services():
    """Get list of enabled user services"""
    rc, out, _ = run(['systemctl', '--user', 'list-unit-files', '--state=enabled'])
    services = []
    for ln in out.splitlines():
        if '.service' in ln and 'enabled' in ln:
            services.append(ln.split()[0])
    return services

def snapshot_all(label=None):
    """Create complete migration snapshot"""
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    label = label or 'migration'
    
    snapshot = {
        'meta': {
            'created': datetime.now().isoformat(),
            'distro': get_distro(),
            'hostname': run(['hostname'])[1],
            'label': label,
        },
        'packages': get_packages(),
        'dotfiles': get_dotfiles(),
        'services': get_services(),
        'gcp_state': {},
    }
    
    # Capture GCP state
    gcp_base = BASE
    if gcp_base.exists():
        for f in ['checkpoints', 'soc/snapshots']:
            p = gcp_base / f
            if p.exists():
                snapshot['gcp_state'][f] = [str(x.relative_to(gcp_base)) for x in p.rglob('*') if x.is_file()]
    
    # Save manifest
    manifest_path = MIGRATIONS_DIR / f'{timestamp}-{label}.json'
    manifest_path.write_text(json.dumps(snapshot, indent=2))
    
    # Create tarball of dotfiles
    archive_path = MIGRATIONS_DIR / f'{timestamp}-{label}-dotfiles.tar.zst'
    
    # Compress with zstd
    with tarfile.open(str(archive_path).replace('.zst', ''), 'w') as tar:
        for df in snapshot['dotfiles'][:100]:  # Limit for size
            p = HOME / df
            if p.exists():
                tar.add(p, arcname=df)
    
    # Compress with zstd if available
    if shutil.which('zstd'):
        run(['zstd', '-f', str(archive_path).replace('.zst', '')])
        Path(str(archive_path).replace('.zst', '')).unlink(missing_ok=True)
    
    print(f'migration snapshot: {manifest_path}')
    print(f'  packages: {len(snapshot["packages"])}')
    print(f'  dotfiles: {len(snapshot["dotfiles"])}')
    print(f'  services: {len(snapshot["services"])}')
    print(f'  archive: {archive_path}')
    
    return manifest_path

def list_snapshots():
    """List available migration snapshots"""
    snaps = sorted(MIGRATIONS_DIR.glob('*.json'))
    if not snaps:
        print('no migration snapshots')
        return
    
    print('migration snapshots:')
    for s in snaps:
        data = json.loads(s.read_text())
        meta = data.get('meta', {})
        print(f"  {s.stem}: {meta.get('distro')} @ {meta.get('created', 'unknown')[:10]}")

def restore_prepare(snapshot_file):
    """Generate restore script from snapshot"""
    snap_path = MIGRATIONS_DIR / snapshot_file
    if not snap_path.exists():
        print(f'snapshot not found: {snapshot_file}')
        return 1
    
    data = json.loads(snap_path.read_text())
    
    print('restore preparation:')
    print()
    print('1. install packages:')
    current_distro = get_distro()
    original_distro = data['meta']['distro']
    
    if current_distro != original_distro:
        print(f'  warning: migrating from {original_distro} to {current_distro}')
        print('  manual package mapping required')
    
    print(f'  # {len(data["packages"])} packages in original')
    if shutil.which('pacman'):
        print(f'  sudo pacman -S {" ".join(data["packages"][:10])} ...')
    elif shutil.which('apt'):
        print(f'  sudo apt install {" ".join(data["packages"][:10])} ...')
    
    print()
    print('2. restore dotfiles:')
    print(f'  tar -xvf {snap_path.stem}-dotfiles.tar.zst -C ~')
    
    print()
    print('3. enable services:')
    for svc in data['services'][:5]:
        print(f'  systemctl --user enable {svc}')
    if len(data['services']) > 5:
        print(f'  # ... and {len(data["services"]) - 5} more')
    
    print()
    print('4. restore gcp:')
    print('  gcp checkpoint restore --file <checkpoint>')
    
    return 0

def export_iso(target_path):
    """Export full migration to portable format"""
    print(f'exporting migration bundle to {target_path}...')
    
    # Create comprehensive bundle
    manifest = snapshot_all('export')
    
    bundle = target_path
    bundle.parent.mkdir(parents=True, exist_ok=True)
    
    # Tar everything together
    with tarfile.open(bundle, 'w:xz') as tar:
        # Add manifest
        tar.add(manifest, arcname='manifest.json')
        
        # Add dotfiles archive if exists
        dotfiles = manifest.parent / f'{manifest.stem}-dotfiles.tar.zst'
        if dotfiles.exists():
            tar.add(dotfiles, arcname='dotfiles.tar.zst')
        
        # Add GCP config
        gcp_dir = HOME / '.openclaw' / 'workspace' / 'ghost-control-plane'
        if gcp_dir.exists():
            tar.add(gcp_dir, arcname='ghost-control-plane')
    
    print(f'bundle created: {bundle}')
    print(f'size: {bundle.stat().st_size / 1024 / 1024:.1f} MB')

def main():
    parser = argparse.ArgumentParser(description='Distro-hop assistant')
    sub = parser.add_subparsers(dest='cmd')
    
    p = sub.add_parser('snapshot')
    p.add_argument('--label')
    
    sub.add_parser('list', help='list migration snapshots')
    
    p = sub.add_parser('restore')
    p.add_argument('snapshot', help='snapshot file to restore from')
    
    p = sub.add_parser('export')
    p.add_argument('path', help='target path for bundle')
    
    args = parser.parse_args()
    
    if args.cmd == 'snapshot':
        snapshot_all(args.label)
    elif args.cmd == 'list':
        list_snapshots()
    elif args.cmd == 'restore':
        restore_prepare(args.snapshot)
    elif args.cmd == 'export':
        export_iso(Path(args.path))
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
