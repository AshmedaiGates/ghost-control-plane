#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parent.parent

PROJECT_HOOKS = {
    'python': {
        'pre-commit': [
            'black --check . || black .',
            'flake8 . --max-line-length=100 || true',
            'python -m pytest --co -q || true',
        ],
    },
    'node': {
        'pre-commit': [
            'npm run lint || true',
            'npm run test -- --passWithNoTests || true',
        ],
    },
    'rust': {
        'pre-commit': [
            'cargo fmt -- --check || cargo fmt',
            'cargo clippy -- -D warnings || true',
            'cargo test --no-run || true',
        ],
    },
    'go': {
        'pre-commit': [
            'gofmt -l . || true',
            'go vet ./... || true',
            'go test -c ./... || true',
        ],
    },
}

def run(cmd, cwd=None):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()

def detect_project_type(path: Path):
    markers = {
        'python': ['requirements.txt', 'pyproject.toml', 'setup.py'],
        'node': ['package.json'],
        'rust': ['Cargo.toml'],
        'go': ['go.mod'],
    }
    for ptype, files in markers.items():
        for f in files:
            if (path / f).exists():
                return ptype
    return None

def install_hooks(path: str):
    p = Path(path).expanduser().resolve()
    ptype = detect_project_type(p)
    
    if not ptype:
        print(f'no recognized project type in {p}')
        return 1
    
    print(f'detected: {ptype}')
    
    hooks_dir = p / '.git' / 'hooks'
    if not hooks_dir.exists():
        print('no .git/hooks directory found')
        return 1
    
    config = PROJECT_HOOKS.get(ptype, {})
    
    for hook_name, commands in config.items():
        hook_path = hooks_dir / hook_name
        
        script = f'''#!/bin/sh
# Ghost Control Plane auto-generated hook for {ptype}
echo "[{hook_name}] Running {ptype} checks..."
{chr(10).join(commands)}
'''
        hook_path.write_text(script)
        hook_path.chmod(0o755)
        print(f'installed: {hook_path}')
    
    print(f'\n{ptype} hooks installed in {p}')
    return 0

def uninstall_hooks(path: str):
    p = Path(path).expanduser().resolve()
    hooks_dir = p / '.git' / 'hooks'
    
    for hook in ['pre-commit', 'pre-push']:
        hook_path = hooks_dir / hook
        if hook_path.exists():
            content = hook_path.read_text()
            if 'Ghost Control Plane' in content:
                hook_path.unlink()
                print(f'removed: {hook_path}')
    
    print('hooks uninstalled')
    return 0

def status(path: str):
    p = Path(path).expanduser().resolve()
    hooks_dir = p / '.git' / 'hooks'
    
    print(f'checking: {p}')
    ptype = detect_project_type(p)
    print(f'detected type: {ptype or "unknown"}')
    
    for hook in ['pre-commit', 'pre-push']:
        hook_path = hooks_dir / hook
        if hook_path.exists():
            content = hook_path.read_text()
            if 'Ghost Control Plane' in content:
                print(f'  {hook}: installed (gcp)')
            else:
                print(f'  {hook}: exists (custom)')
        else:
            print(f'  {hook}: not installed')
    
    return 0

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Git hooks installer')
    sub = parser.add_subparsers(dest='cmd')
    
    p = sub.add_parser('install')
    p.add_argument('path', nargs='?', default='.')
    
    p = sub.add_parser('uninstall')
    p.add_argument('path', nargs='?', default='.')
    
    p = sub.add_parser('status')
    p.add_argument('path', nargs='?', default='.')
    
    args = parser.parse_args()
    
    if args.cmd == 'install':
        sys.exit(install_hooks(args.path))
    elif args.cmd == 'uninstall':
        sys.exit(uninstall_hooks(args.path))
    elif args.cmd == 'status':
        sys.exit(status(args.path))
    else:
        parser.print_help()
