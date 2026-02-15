#!/usr/bin/env python3
import argparse
import subprocess


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    print(f"$ {' '.join(cmd)}")
    if p.stdout:
        print(p.stdout.strip())
    if p.stderr:
        print(p.stderr.strip())
    print('')
    return p.returncode


def main():
    parser = argparse.ArgumentParser(description='Domain-focused read-only checks')
    parser.add_argument('domain', choices=['network', 'dev', 'storage', 'security', 'automation'])
    args = parser.parse_args()

    d = args.domain
    if d == 'network':
        run(['resolvectl', 'status'])
        run(['nmcli', '-t', '-f', 'GENERAL.DEVICE,GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS', 'device', 'show'])
        run(['ss', '-s'])
    elif d == 'dev':
        run(['systemd-analyze', 'blame'])
        run(['python', '--version'])
        run(['node', '--version'])
    elif d == 'storage':
        run(['lsblk', '-o', 'NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,ROTA,SCHED,MODEL'])
        run(['findmnt', '-no', 'TARGET,SOURCE,FSTYPE,OPTIONS', '/', '/home', '/boot'])
        run(['systemctl', 'is-enabled', 'fstrim.timer'])
        run(['systemctl', 'is-active', 'fstrim.timer'])
    elif d == 'security':
        run(['openclaw', 'security', 'audit', '--deep'])
        run(['sudo', '-n', 'ufw', 'status', 'verbose'])
        run(['systemctl', '--failed', '--no-legend'])
    elif d == 'automation':
        run(['systemctl', '--user', 'list-timers', '--all'])
        run(['openclaw', 'cron', 'list'])


if __name__ == '__main__':
    main()
