#!/usr/bin/env python3
import argparse
import json
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG = ROOT.parent / 'config' / 'mesh-policy.json'


def load_policy():
    if CFG.exists():
        return json.loads(CFG.read_text())
    return {
        'safeByDefault': True,
        'allowApplyByDefault': False,
        'maxCommandSeconds': 120,
        'intents': {}
    }


def run(cmd, timeout_s=120):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def pick_intent(task: str):
    t = (task or '').lower()
    if any(k in t for k in ['drift', 'ports', 'firewall', 'exposure']):
        return 'drift'
    if any(k in t for k in ['health', 'guard', 'status']):
        return 'health'
    if any(k in t for k in ['snapshot', 'baseline']):
        return 'snapshot'
    if any(k in t for k in ['repair', 'fix', 'heal', 'stabilize']):
        return 'stabilize'
    if any(k in t for k in ['battery', 'power saver']):
        return 'scene'
    if any(k in t for k in ['performance', 'boost', 'gaming', 'code mode']):
        return 'scene'
    if any(k in t for k in ['autopilot', 'auto mode']):
        return 'autopilot'
    if any(k in t for k in ['repro', 'restore', 'manifest']):
        return 'repro'
    if any(k in t for k in ['round', 'ops', 'daily check']):
        return 'ops-round'
    return 'health'


def intent_plan(intent, apply=False, task=''):
    py = ['python']
    if intent == 'health':
        return [py + [str(ROOT / 'gcp_guard.py'), '--last', '6']]
    if intent == 'drift':
        return [py + [str(ROOT / 'gcp_soc.py'), '--report']]
    if intent == 'snapshot':
        return [py + [str(ROOT / 'gcp_snapshot.py')]]
    if intent == 'stabilize':
        return [py + [str(ROOT / 'gcp_selfheal.py'), '--apply' if apply else '--dry-run']]
    if intent == 'autopilot':
        return [py + [str(ROOT / 'gcp_autopilot.py'), '--apply' if apply else '--dry-run']]
    if intent == 'scene':
        scene = 'focus'
        tl = task.lower()
        if any(k in tl for k in ['battery', 'travel']):
            scene = 'travel'
        elif any(k in tl for k in ['game', 'gaming']):
            scene = 'game'
        elif any(k in tl for k in ['code', 'compile', 'build']):
            scene = 'code'
        cmd = py + [str(ROOT / 'gcp_scene.py'), '--scene', scene, '--apply' if apply else '--dry-run']
        return [cmd]
    if intent == 'repro':
        return [py + [str(ROOT / 'gcp_repro.py'), '--apply' if apply else '--dry-run']]
    if intent == 'ops-round':
        return [
            py + [str(ROOT / 'gcp_guard.py'), '--last', '6'],
            py + [str(ROOT / 'gcp_soc.py'), '--report'],
            py + [str(ROOT / 'gcp_autopilot.py'), '--dry-run'],
        ]
    return [py + [str(ROOT / 'gcp_guard.py'), '--last', '6']]


parser = argparse.ArgumentParser(description='Ghost AI mesh orchestrator (safe-by-default)')
parser.add_argument('--task', default='', help='freeform task text')
parser.add_argument('--intent', choices=['health', 'drift', 'snapshot', 'stabilize', 'autopilot', 'scene', 'repro', 'ops-round'])
parser.add_argument('--explain', action='store_true', help='show routing rationale')
parser.add_argument('--run', action='store_true', help='execute selected plan')
parser.add_argument('--apply', action='store_true', help='allow state-changing variant for apply-capable intents')
parser.add_argument('--allow-apply', action='store_true', help='explicit policy gate for apply actions')
parser.add_argument('--json', action='store_true', help='print machine-readable output')
args = parser.parse_args()

policy = load_policy()
intent = args.intent or pick_intent(args.task)
intent_cfg = (policy.get('intents') or {}).get(intent, {})
allow_by_intent = bool(intent_cfg.get('allowApply', False))
apply_requested = bool(args.apply)
apply_allowed = allow_by_intent and bool(args.allow_apply)
apply_effective = apply_requested and apply_allowed

plan = intent_plan(intent, apply=apply_effective, task=args.task)

summary = {
    'intent': intent,
    'task': args.task,
    'safeByDefault': bool(policy.get('safeByDefault', True)),
    'applyRequested': apply_requested,
    'applyAllowed': apply_allowed,
    'applyEffective': apply_effective,
    'commands': [' '.join(shlex.quote(x) for x in cmd) for cmd in plan],
}

if args.json:
    print(json.dumps(summary, indent=2))
else:
    print(f"intent={intent} applyEffective={apply_effective}")
    for c in summary['commands']:
        print('plan: ' + c)
    if apply_requested and not apply_allowed:
        print('policy: apply denied (use --allow-apply and ensure intent supports apply)')

if args.explain:
    print('explain: route chosen by task keyword matching + policy gate enforcement')

if args.run:
    timeout_s = int(policy.get('maxCommandSeconds', 120))
    for i, cmd in enumerate(plan, 1):
        print(f'run[{i}/{len(plan)}]: ' + ' '.join(shlex.quote(x) for x in cmd))
        rc, out, err = run(cmd, timeout_s=timeout_s)
        print(f'rc={rc}')
        if out:
            print(out)
        if err:
            print(err)
        if rc != 0:
            raise SystemExit(rc)
