#!/usr/bin/env python3
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / 'gcp_profile.py'


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()
    except FileNotFoundError as e:
        return 127, '', str(e)


def ac_online():
    ps = Path('/sys/class/power_supply')
    if not ps.exists():
        return None

    found_mains = False
    for dev in ps.iterdir():
        try:
            tfile = dev / 'type'
            ofile = dev / 'online'
            if tfile.exists() and ofile.exists() and tfile.read_text().strip() == 'Mains':
                found_mains = True
                if ofile.read_text().strip() == '1':
                    return True
        except Exception:
            pass

    if found_mains:
        return False

    # Fallback patterns used on some distros/laptops
    for pat in ('AC*/online', 'ADP*/online'):
        for p in ps.glob(pat):
            try:
                return p.read_text().strip() == '1'
            except Exception:
                pass

    return None


def battery_capacity():
    ps = Path('/sys/class/power_supply')
    if not ps.exists():
        return None

    for dev in ps.iterdir():
        try:
            tfile = dev / 'type'
            cfile = dev / 'capacity'
            if tfile.exists() and cfile.exists() and tfile.read_text().strip() == 'Battery':
                return int(cfile.read_text().strip())
        except Exception:
            pass

    for p in ps.glob('BAT*/capacity'):
        try:
            return int(p.read_text().strip())
        except Exception:
            pass

    return None


def cpu_temp():
    rc, out, _ = run(['sensors'])
    if rc != 0:
        return None
    for ln in out.splitlines():
        if 'Tctl:' in ln or 'Package id 0:' in ln:
            m = re.search(r'(-?\d+(?:\.\d+)?)', ln)
            if m:
                return float(m.group(1))
    return None


def decide_profile(ac, batt, temp):
    # Max-lock mode: always prefer full performance.
    return 'performance', 'Max-lock policy: always performance'


parser = argparse.ArgumentParser(description='Ghost autopilot profile selector (safe)')
parser.add_argument('--apply', action='store_true', help='apply selected profile')
parser.add_argument('--dry-run', action='store_true', help='show decision only')
parser.add_argument('--verify-seconds', type=int, default=15)
args = parser.parse_args()

ac = ac_online()
batt = battery_capacity()
temp = cpu_temp()
profile, reason = decide_profile(ac, batt, temp)

print(f'ac_online={ac} battery={batt} cpu_temp_c={temp}')
print(f'decision={profile} reason="{reason}"')

if args.apply and not args.dry_run:
    cmd = [
        'python', str(PROFILE),
        '--profile', profile,
        '--apply',
        '--verify-seconds', str(max(1, args.verify_seconds)),
    ]
    print('apply: ' + ' '.join(cmd))
    rc, out, err = run(cmd)
    if out:
        print(out)
    if err:
        print(err)
    raise SystemExit(rc)
