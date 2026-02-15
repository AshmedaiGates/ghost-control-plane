#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

HOME = Path.home()
CACHE_ROOT = HOME / '.cache'


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)
    return p


def setup_ccache():
    # ccache setup
    ccache_dir = ensure_dir(CACHE_ROOT / 'ccache')
    rc, out, err = run(['ccache', '--set-config=cache_dir=' + str(ccache_dir)])
    rc2, out2, err2 = run(['ccache', '--set-config=max_size=10G'])

    # Shell integration (fish)
    fish_conf = HOME / '.config' / 'fish' / 'conf.d' / 'ccache.fish'
    content = '''# ccache acceleration
if command -sq ccache
    set -gx CCACHE_DIR ~/.cache/ccache
    set -gx CCACHE_MAXSIZE 10G
    # Wrap common compilers
    if not functions -q gcc 2>/dev/null
        function gcc --wraps gcc
            ccache gcc $argv
        end
    end
    if not functions -q g++ 2>/dev/null
        function g++ --wraps g++
            ccache g++ $argv
        end
    end
    if not functions -q cc 2>/dev/null
        function cc --wraps cc
            ccache cc $argv
        end
    end
end
'''
    fish_conf.write_text(content)
    return {'ccache_dir': str(ccache_dir), 'fish_conf': str(fish_conf)}


def setup_sccache():
    # sccache setup (Rust/cargo accelerator)
    ensure_dir(CACHE_ROOT / 'sccache')
    fish_conf = HOME / '.config' / 'fish' / 'conf.d' / 'sccache.fish'
    content = '''# sccache for Rust/Cargo
if command -sq sccache
    set -gx SCCACHE_CACHE_SIZE 10G
    set -gx SCCACHE_DIR ~/.cache/sccache
    set -gx RUSTC_WRAPPER sccache
end
'''
    fish_conf.write_text(content)
    return {'sccache_dir': str(CACHE_ROOT / 'sccache'), 'fish_conf': str(fish_conf)}


def setup_pnpm_cache():
    # pnpm store location
    if not shutil.which('pnpm'):
        return {'pnpm_store': 'skipped (pnpm not found)'}
    pnpm_store = ensure_dir(HOME / '.local' / 'share' / 'pnpm-store')
    rc, out, _ = run(['pnpm', 'config', 'set', 'store-dir', str(pnpm_store)])
    return {'pnpm_store': str(pnpm_store), 'rc': rc}


def setup_pip_cache():
    # pip cache dir
    pip_cache = ensure_dir(CACHE_ROOT / 'pip')
    # Set in environment via fish
    fish_conf = HOME / '.config' / 'fish' / 'conf.d' / 'pip-cache.fish'
    content = f'''# pip cache acceleration
set -gx PIP_CACHE_DIR {pip_cache}
'''
    fish_conf.write_text(content)
    return {'pip_cache': str(pip_cache), 'fish_conf': str(fish_conf)}


def show_status():
    caches = {
        'ccache': CACHE_ROOT / 'ccache',
        'sccache': CACHE_ROOT / 'sccache',
        'pip': CACHE_ROOT / 'pip',
        'pnpm-store': HOME / '.local' / 'share' / 'pnpm-store',
    }
    for name, path in caches.items():
        size = 'n/a'
        if path.exists():
            rc, out, _ = run(['du', '-sh', str(path)])
            if rc == 0:
                size = out.split()[0]
        print(f'{name}: {path} ({size})')

    # Check ccache stats
    rc, out, _ = run(['ccache', '-s'])
    if rc == 0 and out:
        print('\nccache stats:')
        for ln in out.splitlines()[:10]:
            print('  ' + ln)


def apply_all():
    results = {}
    results['ccache'] = setup_ccache()
    results['sccache'] = setup_sccache()
    results['pnpm'] = setup_pnpm_cache()
    results['pip'] = setup_pip_cache()
    print(json.dumps(results, indent=2))
    print('\nReload fish or run: exec fish')


parser = argparse.ArgumentParser(description='Build cache acceleration setup')
sub = parser.add_subparsers(dest='cmd')
sub.add_parser('status')
sub.add_parser('apply')
args = parser.parse_args()

if args.cmd == 'status':
    show_status()
elif args.cmd == 'apply':
    apply_all()
else:
    parser.print_help()
