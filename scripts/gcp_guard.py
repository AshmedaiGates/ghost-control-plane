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
    vals = [v for v in vals if isinstance(v, (int, float))]
    return (sum(vals) / len(vals)) if vals else None


def calc_penalty_temp(temp, start, scale, cap):
    if temp is None or temp <= start:
        return 0.0
    return min(cap, (temp - start) * scale)


def calc_score(cpu_temp, nvme_temp, errors_last_15m, failed_units):
    cpu_pen = calc_penalty_temp(cpu_temp, start=70.0, scale=1.2, cap=30.0)
    nvme_pen = calc_penalty_temp(nvme_temp, start=60.0, scale=1.0, cap=20.0)
    err_pen = min(25.0, max(0.0, errors_last_15m or 0.0) * 2.0)
    fail_pen = min(30.0, max(0.0, failed_units or 0.0) * 6.0)

    score = max(0, min(100, round(100.0 - (cpu_pen + nvme_pen + err_pen + fail_pen))))
    return score, cpu_pen, nvme_pen, err_pen, fail_pen


parser = argparse.ArgumentParser(description='Read-only guard score for recent snapshots')
parser.add_argument('--last', type=int, default=6, help='number of latest snapshots to inspect')
args = parser.parse_args()

last = max(1, args.last)
files, data = load_recent(last)
print(f'Snapshots analyzed: {len(data)}/{last}')

if not data:
    print(f'No snapshots found in: {BASE}')
    raise SystemExit(0)

cpu_temp = avg([d.get('cpu_temp_c') for d in data])
nvme_temp = avg([d.get('nvme_temp_c') for d in data])
errors_last_15m = avg([d.get('errors_last_15m', 0) or 0 for d in data])
failed_units = avg([d.get('failed_units', 0) or 0 for d in data])

score, cpu_pen, nvme_pen, err_pen, fail_pen = calc_score(cpu_temp, nvme_temp, errors_last_15m, failed_units)
status = 'PASS' if score >= 75 else 'WARN'

cpu_text = f'{cpu_temp:.1f}C' if cpu_temp is not None else 'n/a'
nvme_text = f'{nvme_temp:.1f}C' if nvme_temp is not None else 'n/a'
print(f'Health: {status} score={score}/100')
print(
    f'cpu={cpu_text} nvme={nvme_text} '
    f'err15m_avg={errors_last_15m:.1f} failed_units_avg={failed_units:.1f}'
)
print(
    f'penalties cpu={cpu_pen:.1f} nvme={nvme_pen:.1f} '
    f'errors={err_pen:.1f} failed={fail_pen:.1f}'
)
