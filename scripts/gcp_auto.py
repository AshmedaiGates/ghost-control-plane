#!/usr/bin/env python3
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parent.parent
BASE = HOME / '.local' / 'share' / 'ghost-control-plane'
INSIGHTS_FILE = BASE / 'insights.json'
RULES_FILE = BASE / 'auto-rules.json'
ACTIONS_LOG = BASE / 'actions.log'

def load_json(path, default=None):
    if path.exists():
        return json.loads(path.read_text())
    return default or {}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))

def analyze_patterns():
    """Analyze actions.log to find patterns worth automating"""
    insights = {
        'scenes': {},
        'commands': {},
        'times': {},
        'suggestions': [],
    }
    
    if not ACTIONS_LOG.exists():
        return insights
    
    with open(ACTIONS_LOG) as f:
        for ln in f:
            ln = ln.strip()
            if 'scene' in ln and '--apply' in ln:
                m = re.search(r'scene (\w+)', ln)
                if m:
                    scene = m.group(1)
                    insights['scenes'][scene] = insights['scenes'].get(scene, 0) + 1
            
            # Time-based patterns
            if '[' in ln and ']' in ln:
                ts = ln[1:ln.find(']')]
                try:
                    hour = datetime.fromisoformat(ts).hour
                    insights['times'][hour] = insights['times'].get(hour, 0) + 1
                except:
                    pass
    
    # Generate suggestions
    if insights['scenes']:
        top_scene = max(insights['scenes'], key=insights['scenes'].get)
        count = insights['scenes'][top_scene]
        if count >= 3:
            insights['suggestions'].append({
                'type': 'auto_scene',
                'description': f'You often use "{top_scene}" scene ({count}x). Create a time-based auto-switch?',
                'command': f'gcp auto add scene {top_scene} --when time --value 09:00',
            })
    
    # Battery pattern suggestion
    insights['suggestions'].append({
        'type': 'battery_aware',
        'description': 'Add battery-aware scene switching (auto-switch to travel when unplugged)',
        'command': 'gcp auto add scene travel --when battery --threshold 30',
    })
    
    return insights

def generate_rule(suggestion):
    """Generate an automation rule from a suggestion"""
    rules = load_json(RULES_FILE, [])
    if isinstance(rules, dict):
        rules = []
    
    rule = {
        'id': f"rule_{len(rules)+1:03d}",
        'created': datetime.now().isoformat(),
        'enabled': False,  # Safe-by-default
        'description': suggestion['description'],
        'trigger': {},
        'action': {},
    }
    
    if suggestion['type'] == 'auto_scene':
        # Parse: gcp auto add scene {scene} --when {when} --value {value}
        parts = suggestion['command'].split()
        if len(parts) >= 4:
            rule['trigger'] = {'type': 'time', 'value': '09:00'}
            rule['action'] = {'type': 'scene', 'value': parts[3]}
    
    rules.append(rule)
    save_json(RULES_FILE, rules)
    return rule['id']

def list_rules():
    rules = load_json(RULES_FILE, [])
    if not rules:
        print('no automation rules')
        return
    
    print('automation rules:')
    for r in rules:
        status = 'enabled' if r.get('enabled') else 'disabled'
        print(f"  {r['id']}: {status} - {r['description'][:50]}...")

def toggle_rule(rule_id, enabled=None):
    rules = load_json(RULES_FILE, [])
    for r in rules:
        if r['id'] == rule_id:
            if enabled is None:
                enabled = not r.get('enabled', False)
            r['enabled'] = enabled
            save_json(RULES_FILE, rules)
            print(f"{rule_id}: {'enabled' if enabled else 'disabled'}")
            return
    print(f'rule not found: {rule_id}')

def learn():
    """Main learning loop - analyze and suggest"""
    print('== GCP Self-Learning ==')
    print()
    
    insights = analyze_patterns()
    
    print('observed patterns:')
    if insights['scenes']:
        print(f"  scenes used: {insights['scenes']}")
    if insights['times']:
        peak = max(insights['times'], key=insights['times'].get)
        print(f"  peak activity: {peak}:00 ({insights['times'][peak]} actions)")
    
    print()
    
    if not insights['suggestions']:
        print('no suggestions yet - need more data')
        return
    
    print('suggestions:')
    for i, sug in enumerate(insights['suggestions'], 1):
        print(f"\n  [{i}] {sug['description']}")
        print(f"      proposed: {sug['command']}")
        
        # Auto-generate rule file (disabled by default)
        rule_id = generate_rule(sug)
        print(f"      generated rule: {rule_id} (disabled, review with 'gcp auto list')")
    
    save_json(INSIGHTS_FILE, insights)
    print()

def execute_rules():
    """Execute enabled rules based on conditions"""
    rules = load_json(RULES_FILE, [])
    now = datetime.now()
    
    for r in rules:
        if not r.get('enabled'):
            continue
        
        trigger = r.get('trigger', {})
        action = r.get('action', {})
        
        if trigger.get('type') == 'time':
            # Check if current time matches
            trigger_time = trigger.get('value', '09:00')
            current = now.strftime('%H:%M')
            if current == trigger_time and now.second < 60:
                print(f"executing {r['id']}: {action}")
                # Would execute here

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Self-modifying automation')
    sub = parser.add_subparsers(dest='cmd')
    
    sub.add_parser('learn', help='analyze patterns and suggest rules')
    sub.add_parser('list', help='list automation rules')
    
    p = sub.add_parser('enable')
    p.add_argument('rule_id')
    
    p = sub.add_parser('disable')
    p.add_argument('rule_id')
    
    args = parser.parse_args()
    
    if args.cmd == 'learn':
        learn()
    elif args.cmd == 'list':
        list_rules()
    elif args.cmd == 'enable':
        toggle_rule(args.rule_id, True)
    elif args.cmd == 'disable':
        toggle_rule(args.rule_id, False)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
