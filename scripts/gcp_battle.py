#!/usr/bin/env python3
import argparse
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd, timeout=60):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def network_reset():
    print('== Network reset ==')
    rc, out, err = run(['sudo', '-n', 'resolvectl', 'flush-caches'])
    print(f'flush-caches rc={rc}')
    rc, out, err = run(['nmcli', 'general', 'reload'])
    print(f'nmcli reload rc={rc}')
    rc, out, err = run(['nmcli', 'device', 'reapply'])
    print(f'nmcli reapply rc={rc}')
    print('Network reset complete.')


def kill_stuck():
    print('== Kill stuck processes ==')
    # Find processes using high CPU for extended time
    rc, out, _ = run(['ps', '-eo', 'pid,comm,%cpu', '--sort=-%cpu'])
    lines = out.splitlines()
    killed = []
    for ln in lines[:15]:
        parts = ln.split()
        if len(parts) >= 3:
            try:
                cpu = float(parts[2])
                if cpu > 90.0:
                    pid = parts[0]
                    comm = parts[1]
                    print(f'killing {comm} (pid {pid}, cpu {cpu}%)')
                    run(['kill', '-TERM', pid])
                    killed.append(pid)
            except ValueError:
                pass
    if not killed:
        print('No high-CPU zombies found.')
    else:
        time.sleep(2)
        for pid in killed:
            run(['kill', '-KILL', pid])
        print(f'killed {len(killed)} processes')


def emergency_perf():
    print('== Emergency performance ==')
    # Set performance power profile
    py = ['python', str(ROOT / 'scripts' / 'gcp_profile.py'), '--profile', 'performance', '--apply']
    rc, out, err = run(py)
    if out:
        print(out)
    if err:
        print(err)
    print(f'power profile emergency set rc={rc}')


def memory_free():
    print('== Memory free ==')
    rc, out, _ = run(['free', '-h'])
    if out:
        print('before:')
        print(out)
    # Clear caches (safe)
    rc, out, err = run(['sudo', '-n', 'sync'])
    rc, out, err = run(['sudo', '-n', 'sh', '-c', 'echo 1 > /proc/sys/vm/drop_caches'])
    print(f'drop_caches rc={rc}')
    rc, out, _ = run(['free', '-h'])
    if out:
        print('after:')
        print(out)


def fix_wifi():
    print('== Fix Wi-Fi ==')
    rc, out, _ = run(['nmcli', 'radio', 'wifi', 'off'])
    time.sleep(2)
    rc, out, _ = run(['nmcli', 'radio', 'wifi', 'on'])
    print('Wi-Fi toggled.')


parser = argparse.ArgumentParser(description='Emergency battle commands')
sub = parser.add_subparsers(dest='cmd')
sub.add_parser('network-reset', help='flush DNS + restart network')
sub.add_parser('kill-stuck', help='kill high-CPU zombies')
sub.add_parser('emergency-perf', help='force performance power profile')
sub.add_parser('memory-free', help='clear caches')
sub.add_parser('fix-wifi', help='toggle Wi-Fi radio')
sub.add_parser('all', help='run network-reset + emergency-perf + memory-free')
args = parser.parse_args()

if args.cmd == 'network-reset':
    network_reset()
elif args.cmd == 'kill-stuck':
    kill_stuck()
elif args.cmd == 'emergency-perf':
    emergency_perf()
elif args.cmd == 'memory-free':
    memory_free()
elif args.cmd == 'fix-wifi':
    fix_wifi()
elif args.cmd == 'all':
    network_reset()
    emergency_perf()
    memory_free()
else:
    parser.print_help()
