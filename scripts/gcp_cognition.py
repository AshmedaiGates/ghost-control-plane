#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
from pathlib import Path

HOME = Path.home()
COGNITION_DIR = HOME / '.config' / 'ghost-control-plane' / 'cognition'
COGNITION_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_TYPES = {
    'python': {
        'markers': ['requirements.txt', 'pyproject.toml', 'setup.py', 'Pipfile'],
        'extensions': ['.py'],
        'venv_dirs': ['.venv', 'venv', '.env', 'env'],
        'env_files': ['.env', '.env.local'],
    },
    'node': {
        'markers': ['package.json', 'pnpm-lock.yaml', 'yarn.lock', 'package-lock.json'],
        'extensions': ['.js', '.ts', '.mjs'],
        'env_files': ['.env', '.env.local', '.env.development'],
    },
    'rust': {
        'markers': ['Cargo.toml'],
        'extensions': ['.rs'],
        'env_files': ['.env'],
    },
    'go': {
        'markers': ['go.mod'],
        'extensions': ['.go'],
        'env_files': ['.env'],
    },
}


def detect_project_type(path: Path):
    for ptype, config in PROJECT_TYPES.items():
        # Check markers
        for marker in config.get('markers', []):
            if (path / marker).exists():
                return ptype, config
        # Check extensions (also in subdirectories)
        for ext in config.get('extensions', []):
            if list(path.rglob(f'*{ext}')):
                return ptype, config
    return None, {}


def find_venv(path: Path, ptype: str, config: dict):
    if ptype == 'python':
        for vdir in config.get('venv_dirs', []):
            vpath = path / vdir
            if vpath.exists():
                return vpath
    return None


def load_env_files(path: Path, config: dict):
    loaded = []
    for ef in config.get('env_files', []):
        epath = path / ef
        if epath.exists():
            loaded.append(str(epath))
    return loaded


def read_env_file(epath: Path):
    env = {}
    try:
        with open(epath) as f:
            for ln in f:
                ln = ln.strip()
                if not ln or ln.startswith('#'):
                    continue
                if '=' in ln:
                    k, v = ln.split('=', 1)
                    env[k.strip()] = v.strip().strip('"\'')
    except Exception:
        pass
    return env


def suggest_commands(path: Path, ptype: str, config: dict):
    suggestions = []
    
    if ptype == 'python':
        venv = find_venv(path, ptype, config)
        if venv:
            activate = venv / 'bin' / 'activate'
            if activate.exists():
                suggestions.append(f'source {activate}')
        if (path / 'requirements.txt').exists():
            suggestions.append('pip install -r requirements.txt')
        if (path / 'pyproject.toml').exists():
            suggestions.append('pip install -e .')
    
    elif ptype == 'node':
        if (path / 'pnpm-lock.yaml').exists():
            suggestions.append('pnpm install')
        elif (path / 'yarn.lock').exists():
            suggestions.append('yarn install')
        else:
            suggestions.append('npm install')
        if (path / 'package.json').exists():
            suggestions.append('npm run dev  # or pnpm dev')
    
    elif ptype == 'rust':
        suggestions.append('cargo build')
        suggestions.append('cargo run')
    
    elif ptype == 'go':
        suggestions.append('go mod tidy')
        suggestions.append('go run .')
    
    return suggestions


def analyze(path: str):
    p = Path(path).expanduser().resolve()
    if not p.exists():
        print(f'path not found: {p}')
        return
    
    print(f'analyzing: {p}')
    print()
    
    ptype, config = detect_project_type(p)
    if not ptype:
        print('no recognized project type detected')
        return
    
    print(f'detected: {ptype}')
    print()
    
    # Virtual environment
    venv = find_venv(p, ptype, config)
    if venv:
        print(f'venv: {venv}')
        print()
    
    # Environment files
    env_files = load_env_files(p, config)
    if env_files:
        print(f'env_files:')
        for ef in env_files:
            print(f'  - {ef}')
        print()
    
    # Suggested commands
    suggestions = suggest_commands(p, ptype, config)
    if suggestions:
        print('suggested_commands:')
        for cmd in suggestions:
            print(f'  $ {cmd}')
        print()
    
    # Save cognition state
    state = {
        'path': str(p),
        'type': ptype,
        'venv': str(venv) if venv else None,
        'env_files': env_files,
        'suggestions': suggestions,
    }
    state_file = COGNITION_DIR / 'last.json'
    state_file.write_text(json.dumps(state, indent=2))


def auto_activate(path: str):
    p = Path(path).expanduser().resolve()
    ptype, config = detect_project_type(p)
    if not ptype:
        return
    
    # Output fish commands for auto-activation
    venv = find_venv(p, ptype, config)
    if venv and ptype == 'python':
        activate = venv / 'bin' / 'activate'
        if activate.exists():
            print(f'source {activate}')
    
    # Export env vars from .env files
    for ef in load_env_files(p, config):
        envs = read_env_file(Path(ef))
        for k, v in envs.items():
            print(f'set -gx {k} {v}')


parser = argparse.ArgumentParser(description='Project cognition layer')
sub = parser.add_subparsers(dest='cmd')
sub.add_parser('detect', help='detect project type in current directory')
p = sub.add_parser('analyze')
p.add_argument('path', nargs='?', default='.')
p = sub.add_parser('auto-activate')
p.add_argument('path', nargs='?', default='.')
args = parser.parse_args()

if args.cmd == 'detect':
    ptype, _ = detect_project_type(Path.cwd())
    print(ptype or 'unknown')
elif args.cmd == 'analyze':
    analyze(args.path)
elif args.cmd == 'auto-activate':
    auto_activate(args.path)
else:
    parser.print_help()
