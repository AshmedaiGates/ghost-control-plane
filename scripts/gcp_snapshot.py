#!/usr/bin/env python3
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE = Path.home() / '.local' / 'share' / 'ghost-control-plane'
SNAP = BASE / 'snapshots'
BASE.mkdir(parents=True, exist_ok=True)
SNAP.mkdir(parents=True, exist_ok=True)


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return (p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip())
    except Exception as e:
        return (1, '', str(e))


def first_float(text):
    m = re.search(r'(-?\d+(?:\.\d+)?)', text or '')
    return float(m.group(1)) if m else None


snapshot = {
    'ts': datetime.now(timezone.utc).isoformat(),
    'host': os.uname().nodename,
    'kernel': os.uname().release,
}

# uptime/load
rc, out, _ = run(['uptime'])
snapshot['uptime'] = out if rc == 0 else None

# memory
rc, out, _ = run(['free', '-b'])
if rc == 0 and out:
    lines = out.splitlines()
    mem = [ln for ln in lines if ln.startswith('Mem:')]
    if mem:
        p = mem[0].split()
        if len(p) >= 7:
            total = int(p[1]); used = int(p[2]); avail = int(p[6])
            snapshot['memory'] = {
                'total_b': total,
                'used_b': used,
                'avail_b': avail,
                'used_ratio': round(used / total, 4) if total else None,
            }

# swap
rc, out, _ = run(['swapon', '--show', '--bytes'])
snapshot['swap'] = out if rc == 0 else None

# CPU policy
for key, path in {
    'cpu_governor': '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor',
    'cpu_epp': '/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference',
}.items():
    try:
        with open(path) as f:
            snapshot[key] = f.read().strip()
    except Exception:
        snapshot[key] = None

# boot/userspace timing
rc, out, _ = run(['systemd-analyze'])
snapshot['systemd_analyze'] = out if rc == 0 else None
if out:
    m = re.search(r'\+\s*([0-9.]+)s \(userspace\)', out)
    snapshot['userspace_sec'] = float(m.group(1)) if m else None

# failed units count
rc, out, _ = run(['systemctl', '--failed', '--no-legend'])
if rc == 0:
    snapshot['failed_units'] = len([ln for ln in out.splitlines() if ln.strip()])

# journal errors last 15m
rc, out, _ = run(['journalctl', '--since', '15 min ago', '-p', '0..3', '--no-pager'])
if rc == 0:
    snapshot['errors_last_15m'] = len([ln for ln in out.splitlines() if ln.strip() and not ln.startswith('--')])

# sensors (best effort)
rc, out, _ = run(['sensors'])
if rc == 0:
    snapshot['sensors_raw'] = out
    cpu_temp = None
    nvme_temp = None
    for ln in out.splitlines():
        if 'Tctl:' in ln and cpu_temp is None:
            cpu_temp = first_float(ln)
        if 'Composite:' in ln and nvme_temp is None:
            nvme_temp = first_float(ln)
    snapshot['cpu_temp_c'] = cpu_temp
    snapshot['nvme_temp_c'] = nvme_temp

# nvidia (best effort)
rc, out, _ = run([
    'nvidia-smi',
    '--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,pstate,power.draw',
    '--format=csv,noheader,nounits'
])
if rc == 0 and out:
    snapshot['nvidia_raw'] = out

name = datetime.now().strftime('%Y%m%d-%H%M%S') + '.json'
path = SNAP / name
path.write_text(json.dumps(snapshot, indent=2))
print(str(path))
