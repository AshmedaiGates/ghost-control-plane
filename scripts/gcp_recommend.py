#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

BASE = Path.home() / '.local' / 'share' / 'ghost-control-plane' / 'snapshots'


def load_recent(n):
    files = sorted(BASE.glob('*.json'))[-n:]
    data = []
    for f in files:
        try:
            data.append(json.loads(f.read_text()))
        except Exception:
            pass
    return files, data


def avg(vals):
    vals = [v for v in vals if v is not None]
    return (sum(vals) / len(vals)) if vals else None


parser = argparse.ArgumentParser(description='Recommend safe tuning actions from snapshots')
parser.add_argument('--last', type=int, default=24, help='number of recent snapshots to inspect')
args = parser.parse_args()

files, data = load_recent(args.last)
print(f'Snapshots analyzed: {len(data)}')
if not data:
    print('No snapshots found. Run: python scripts/gcp_snapshot.py')
    raise SystemExit(0)

cpu_t = avg([d.get('cpu_temp_c') for d in data])
nvme_t = avg([d.get('nvme_temp_c') for d in data])
mem_u = avg([((d.get('memory') or {}).get('used_ratio')) for d in data])
userspace = avg([d.get('userspace_sec') for d in data])
errs = sum([d.get('errors_last_15m', 0) or 0 for d in data])

print('\nSummary')
print(f'- Avg CPU temp: {cpu_t:.1f} C' if cpu_t is not None else '- Avg CPU temp: n/a')
print(f'- Avg NVMe temp: {nvme_t:.1f} C' if nvme_t is not None else '- Avg NVMe temp: n/a')
print(f'- Avg memory used ratio: {mem_u:.2f}' if mem_u is not None else '- Avg memory used ratio: n/a')
print(f'- Avg userspace boot sec: {userspace:.2f}s' if userspace is not None else '- Avg userspace boot sec: n/a')
print(f'- Total p0..p3 log lines across samples: {errs}')

print('\nSafe recommendations')
recs = []
if userspace and userspace > 12:
    recs.append('Keep persistent=false on plocate/man-db timers (already safe and applied).')
if mem_u and mem_u > 0.90:
    recs.append('Investigate high-memory apps before changing kernel/vm settings.')
if cpu_t and cpu_t > 85:
    recs.append('Switch to balanced profile on battery or raise fan curve in OEM tools.')
if nvme_t and nvme_t > 70:
    recs.append('Audit sustained IO workload; ensure airflow/thermal pad health.')
if not recs:
    recs.append('System looks healthy. Keep current profile and periodic checks.')

for r in recs:
    print(f'- {r}')

print('\nNext commands')
print('- python scripts/gcp_profile.py --list')
print('- python scripts/gcp_profile.py --profile balanced --dry-run')
