#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path.home() / '.local' / 'share' / 'ghost-control-plane'
BASE.mkdir(parents=True, exist_ok=True)
LOG = BASE / 'actions.log'
MAX_CPU_TEMP_C = 90.0
MAX_P0P3_LINES = 10

PROFILES = {
    'balanced': [('powerprofilesctl', ['set', 'balanced'])],
    'performance': [('powerprofilesctl', ['set', 'performance'])],
    'battery': [('powerprofilesctl', ['set', 'power-saver'])],
    # focus keeps balanced power but lowers background aggressiveness by policy only if tools exist
    'focus': [('powerprofilesctl', ['set', 'balanced'])],
}


def has(cmd):
    return shutil.which(cmd) is not None


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()
    except Exception as e:
        return 1, '', str(e)


def first_float(text):
    m = re.search(r'(-?\d+(?:\.\d+)?)', text or '')
    return float(m.group(1)) if m else None


def append_log(message):
    line = f"{datetime.now().isoformat()} {message}\n"
    with LOG.open('a') as f:
        f.write(line)


def powerprofilesctl_cmd(args):
    # Force the system Python + system powerprofilesctl so Homebrew python3 on PATH
    # does not break gi imports required by /usr/bin/powerprofilesctl.
    if Path('/usr/bin/powerprofilesctl').exists() and Path('/usr/bin/python').exists():
        return ['/usr/bin/python', '/usr/bin/powerprofilesctl'] + args
    if has('powerprofilesctl'):
        return ['powerprofilesctl'] + args
    return None


def get_power_profile():
    cmd = powerprofilesctl_cmd(['get'])
    if not cmd:
        return None, 'powerprofilesctl missing'
    rc, out, err = run(cmd)
    if rc != 0 or not out:
        return None, err or f'rc={rc}'
    return out.strip(), None


def restore_power_profile(profile):
    if not profile:
        return False, 'previous profile unknown'
    cmd = powerprofilesctl_cmd(['set', profile])
    if not cmd:
        return False, 'powerprofilesctl missing'
    rc, out, err = run(cmd)
    msg = out or err or f'rc={rc}'
    return rc == 0, msg


def read_cpu_temp_c():
    if not has('sensors'):
        return None, 'sensors missing'
    rc, out, err = run(['sensors'])
    if rc != 0:
        return None, err or f'rc={rc}'

    preferred_labels = ('Tctl:', 'Package id 0:', 'Tdie:', 'CPU:', 'edge:')
    for ln in out.splitlines():
        if any(label in ln for label in preferred_labels):
            val = first_float(ln)
            if val is not None:
                return val, None

    for ln in out.splitlines():
        if '°C' in ln or ' C' in ln:
            val = first_float(ln)
            if val is not None:
                return val, None
    return None, 'no temperature line found'


def read_journal_p0p3_count(verify_seconds):
    if not has('journalctl'):
        return None, 'journalctl missing'
    since = f'{max(1, verify_seconds)} sec ago'
    rc, out, err = run(['journalctl', '--since', since, '-p', '0..3', '--no-pager'])
    if rc != 0:
        return None, err or f'rc={rc}'
    count = 0
    for ln in out.splitlines():
        s = ln.strip()
        if not s or s.startswith('--'):
            continue
        count += 1
    return count, None


def regression_reasons(cpu_temp_c, p0p3_lines):
    reasons = []
    if cpu_temp_c is not None and cpu_temp_c > MAX_CPU_TEMP_C:
        reasons.append(f'cpu_temp_c={cpu_temp_c:.1f} > {MAX_CPU_TEMP_C:.1f}')
    if p0p3_lines is not None and p0p3_lines > MAX_P0P3_LINES:
        reasons.append(f'p0p3_lines={p0p3_lines} > {MAX_P0P3_LINES}')
    return reasons


parser = argparse.ArgumentParser(description='Apply safe runtime profiles')
parser.add_argument('--list', action='store_true', help='list available profiles')
parser.add_argument('--profile', choices=sorted(PROFILES.keys()))
parser.add_argument('--apply', action='store_true', help='actually apply changes')
parser.add_argument('--dry-run', action='store_true', help='show commands only')
parser.add_argument('--verify-seconds', type=int, default=30, help='post-apply verification window in seconds')
parser.add_argument('--rollback-on-regression', dest='rollback_on_regression', action='store_true',
                    help='rollback safe runtime profile when regression is detected (default)')
parser.add_argument('--no-rollback-on-regression', dest='rollback_on_regression', action='store_false',
                    help='do not rollback if regression is detected')
parser.set_defaults(rollback_on_regression=True)
args = parser.parse_args()

if args.list:
    print('Profiles: ' + ', '.join(sorted(PROFILES.keys())))
    raise SystemExit(0)

if not args.profile:
    parser.error('--profile is required unless --list is used')

steps = PROFILES[args.profile]
mode = 'apply' if args.apply and not args.dry_run else 'dry-run'
print(f'Profile: {args.profile} ({mode})')

previous_power_profile = None
if mode == 'apply':
    previous_power_profile, capture_note = get_power_profile()
    if previous_power_profile:
        print(f'Pre-change power profile: {previous_power_profile}')
    else:
        print(f'Pre-change power profile: unavailable ({capture_note})')

for cmd, a in steps:
    full = [cmd] + a
    run_cmd = full
    if cmd == 'powerprofilesctl':
        alt = powerprofilesctl_cmd(a)
        if alt:
            run_cmd = alt
        else:
            print(f'- skip (missing): {cmd}')
            continue
    elif not has(cmd):
        print(f'- skip (missing): {cmd}')
        continue

    print('- ' + ' '.join(full))
    if mode == 'apply':
        rc, out, err = run(run_cmd)
        print(f'  rc={rc}')
        if out:
            print(f'  out: {out}')
        if err:
            print(f'  err: {err}')

status = 'ok'
regression = 0
cpu_temp_c = None
p0p3_lines = None
verify_seconds = max(1, args.verify_seconds)

if mode == 'apply':
    cpu_temp_c, cpu_note = read_cpu_temp_c()
    p0p3_lines, log_note = read_journal_p0p3_count(verify_seconds)
    print(f'Post-apply safety checks (window={verify_seconds}s)')
    if cpu_temp_c is None:
        print(f'- cpu_temp_c: unavailable ({cpu_note})')
    else:
        print(f'- cpu_temp_c: {cpu_temp_c:.1f} C (limit {MAX_CPU_TEMP_C:.1f} C)')
    if p0p3_lines is None:
        print(f'- journal p0..p3 lines: unavailable ({log_note})')
    else:
        print(f'- journal p0..p3 lines: {p0p3_lines} (limit {MAX_P0P3_LINES})')

    reasons = regression_reasons(cpu_temp_c, p0p3_lines)
    if reasons:
        regression = 1
        if args.rollback_on_regression:
            rollback_ok, rollback_note = restore_power_profile(previous_power_profile)
            status = 'rollback' if rollback_ok else 'rollback-attempted'
            if rollback_ok:
                print(f'ROLLBACK: restored power profile to "{previous_power_profile}"')
            else:
                print(f'ROLLBACK: requested but not completed ({rollback_note})')
            append_log(
                f"profile={args.profile} mode={mode} status={status} regression=1 "
                f"reasons=\"{'; '.join(reasons)}\" prev_power_profile={previous_power_profile or 'unknown'} "
                f"verify_seconds={verify_seconds}"
            )
        else:
            status = 'regression-no-rollback'
            print('Regression detected; rollback disabled by flag.')
            append_log(
                f"profile={args.profile} mode={mode} status={status} regression=1 "
                f"reasons=\"{'; '.join(reasons)}\" prev_power_profile={previous_power_profile or 'unknown'} "
                f"verify_seconds={verify_seconds}"
            )
    else:
        print('Post-apply verification PASS: no regression detected.')
        status = 'applied-ok'
        append_log(
            f"profile={args.profile} mode={mode} status={status} regression=0 "
            f"cpu_temp_c={cpu_temp_c if cpu_temp_c is not None else 'na'} "
            f"p0p3_lines={p0p3_lines if p0p3_lines is not None else 'na'} "
            f"verify_seconds={verify_seconds}"
        )
else:
    append_log(f'profile={args.profile} mode={mode} status=planned regression={regression}')

print(f'Logged: {LOG}')
