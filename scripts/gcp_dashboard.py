#!/usr/bin/env python3
import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = Path.home() / '.local' / 'share' / 'ghost-control-plane'


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def clear():
    print('\033[2J\033[H', end='')


def line(char='-', width=70):
    print(char * width)


def header(title):
    line('=')
    print(f'  {title}')
    line('=')


def section(title):
    line('-')
    print(f'  {title}')
    line('-')


def get_health():
    try:
        _, out, _ = run(['python', str(ROOT / 'gcp_guard.py')])
        for ln in out.splitlines():
            if 'Health:' in ln:
                return ln
    except Exception:
        pass
    return 'Health: unknown'


def get_power_profile():
    try:
        _, out, _ = run(['/usr/bin/python', '/usr/bin/powerprofilesctl', 'get'])
        return out or 'unknown'
    except Exception:
        return 'unknown'


def get_audio_state():
    try:
        snap = json.loads((BASE / 'state' / 'audio-last.json').read_text())
        return f"audio={snap.get('clock.force-quantum','?')}"
    except Exception:
        return 'audio=unknown'


def get_network_dns():
    rc, out, _ = run(['resolvectl', 'status'])
    for ln in out.splitlines():
        if 'Current DNS Server' in ln:
            return ln.strip()
    return 'DNS=unknown'


def get_timers():
    rc, out, _ = run(['systemctl', '--user', 'list-timers', '--all'])
    timers = []
    for ln in out.splitlines():
        if 'gcp-' in ln:
            timers.append(ln.strip())
    return timers[:6]


def get_temps():
    rc, out, _ = run(['sensors'])
    temps = []
    for ln in out.splitlines():
        if 'Tctl:' in ln or 'Composite:' in ln:
            temps.append(ln.strip())
    return temps[:4]


def get_scene():
    # Best effort: guess from power profile
    pp = get_power_profile()
    if pp == 'performance':
        return 'game/code (performance)'
    if pp == 'balanced':
        return 'focus/stream (balanced)'
    if pp == 'power-saver':
        return 'travel (battery)'
    return pp


def dashboard():
    clear()
    header('Ghost Control Plane Dashboard')
    print(f'  Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()

    section('Health & State')
    print(f'  {get_health()}')
    print(f'  power={get_power_profile()}')
    print(f'  scene={get_scene()}')
    print(f'  {get_audio_state()}')
    print(f'  {get_network_dns()}')
    print()

    section('Temperatures')
    for t in get_temps():
        print(f'  {t}')
    print()

    section('Active Timers')
    for t in get_timers():
        print(f'  {t}')
    print()

    section('Quick Commands')
    print('  gcp scene game|code|focus|travel|stream --apply')
    print('  gcp status')
    print('  gcp battle network-reset')
    print()

    print('Press Ctrl+C to exit.')


def live_dashboard(interval=5):
    try:
        while True:
            dashboard()
            time.sleep(interval)
    except KeyboardInterrupt:
        print('\nDashboard exited.')


parser = argparse.ArgumentParser(description='Ghost dashboard')
parser.add_argument('--live', action='store_true', help='auto-refresh mode')
parser.add_argument('--interval', type=int, default=5, help='refresh seconds')
args = parser.parse_args()

if args.live:
    live_dashboard(args.interval)
else:
    dashboard()
