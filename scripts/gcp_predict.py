#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

HOME = Path.home()
BASE = HOME / '.local' / 'share' / 'ghost-control-plane'
PREDICT_DIR = BASE / 'predictive'
PREDICT_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_FILE = PREDICT_DIR / 'hardware_history.jsonl'

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()

def get_nvme_smart(device='nvme0'):
    """Get NVMe SMART data"""
    rc, out, _ = run(['sudo', '-n', 'nvme', 'smart-log', f'/dev/{device}'])
    if rc != 0:
        return {}
    
    data = {}
    for ln in out.splitlines():
        if ':' in ln:
            key, val = ln.split(':', 1)
            key = key.strip().lower().replace(' ', '_')
            val = val.strip()
            # Extract numbers
            m = re.search(r'(\d+)', val)
            if m:
                data[key] = int(m.group(1))
    return data

def get_ssd_smart(device='sda'):
    """Get SATA SSD SMART via smartctl"""
    if not shutil.which('smartctl'):
        return {}
    
    rc, out, _ = run(['sudo', '-n', 'smartctl', '-a', f'/dev/{device}'])
    if rc not in [0, 4]:  # 4 is SMART failing but data available
        return {}
    
    data = {}
    for ln in out.splitlines():
        if 'Wear_Leveling_Count' in ln or 'Percent_Lifetime_Used' in ln:
            m = re.search(r'(\d+)', ln.split()[-1])
            if m:
                data['wear_level'] = int(m.group(1))
        elif 'Temperature' in ln and 'cel' in ln.lower():
            m = re.search(r'(\d+)', ln)
            if m:
                data['temp'] = int(m.group(1))
        elif 'Reallocated_Sector_Ct' in ln:
            m = re.search(r'(\d+)', ln.split()[-1])
            if m:
                data['reallocated_sectors'] = int(m.group(1))
        elif 'Power_On_Hours' in ln:
            m = re.search(r'(\d+)', ln.split()[-1])
            if m:
                data['power_on_hours'] = int(m.group(1))
    
    return data

def get_cpu_temps():
    """Get CPU temperature history"""
    rc, out, _ = run(['sensors', '-u'])
    temps = {}
    current_chip = None
    for ln in out.splitlines():
        if ln.endswith(':'):
            current_chip = ln[:-1].lower()
        elif 'temp1_input' in ln or 'tctl' in ln.lower():
            m = re.search(r'(\d+\.?\d*)', ln.split(':')[-1])
            if m:
                temps['cpu'] = float(m.group(1))
    return temps

def collect_snapshot():
    """Collect hardware health snapshot"""
    snapshot = {
        'timestamp': datetime.now().isoformat(),
        'nvme': get_nvme_smart('nvme0'),
        'ssd': get_ssd_smart('sda'),
        'temps': get_cpu_temps(),
    }
    return snapshot

def save_history(snapshot):
    """Append to historical data"""
    with open(HISTORY_FILE, 'a') as f:
        f.write(json.dumps(snapshot) + '\n')

def load_history(days=30):
    """Load historical data for analysis"""
    history = []
    if not HISTORY_FILE.exists():
        return history
    
    cutoff = datetime.now().timestamp() - (days * 24 * 3600)
    
    with open(HISTORY_FILE) as f:
        for ln in f:
            try:
                entry = json.loads(ln)
                # Parse timestamp
                ts = datetime.fromisoformat(entry['timestamp'])
                if ts.timestamp() > cutoff:
                    history.append(entry)
            except:
                pass
    
    return history

def analyze_trends(history):
    """Simple trend analysis for failure prediction"""
    if len(history) < 3:
        return {'confidence': 'insufficient_data', 'alerts': []}
    
    alerts = []
    
    # NVMe analysis
    nvme_wear = [h['nvme'].get('percentage_used', 0) for h in history if h.get('nvme')]
    if nvme_wear and len(nvme_wear) >= 2:
        current = nvme_wear[-1]
        if current > 90:
            alerts.append({
                'severity': 'CRITICAL',
                'component': 'NVMe',
                'issue': f'SSD wear at {current}%, replacement recommended',
                'eta_days': 'immediate',
            })
        elif current > 70:
            alerts.append({
                'severity': 'WARNING',
                'component': 'NVMe', 
                'issue': f'SSD wear at {current}%, monitor closely',
                'eta_days': '~6 months',
            })
    
    # Temperature trends
    temps = [h['temps'].get('cpu', 0) for h in history if h.get('temps')]
    if len(temps) >= 3:
        avg_recent = sum(temps[-3:]) / 3
        avg_old = sum(temps[:3]) / 3 if len(temps) >= 6 else avg_recent
        
        if avg_recent > avg_old + 10:
            alerts.append({
                'severity': 'WARNING',
                'component': 'CPU',
                'issue': f'Temps rising: {avg_old:.1f}°C → {avg_recent:.1f}°C',
                'suggestion': 'Check thermal paste, fan health',
            })
    
    # SMART critical values
    latest = history[-1]
    if latest.get('ssd', {}).get('reallocated_sectors', 0) > 0:
        alerts.append({
            'severity': 'CRITICAL',
            'component': 'SATA SSD',
            'issue': f'{latest["ssd"]["reallocated_sectors"]} reallocated sectors detected',
            'eta_days': 'backup immediately',
        })
    
    confidence = 'high' if len(history) > 20 else 'medium' if len(history) > 5 else 'low'
    
    return {
        'confidence': confidence,
        'samples': len(history),
        'alerts': alerts,
    }

def predict():
    """Main prediction function"""
    print('== Hardware Failure Prediction ==')
    print()
    
    # Collect current snapshot
    snap = collect_snapshot()
    save_history(snap)
    
    print(f'Current readings:')
    if snap['nvme']:
        wear = snap['nvme'].get('percentage_used', 'unknown')
        print(f'  NVMe wear: {wear}%')
    if snap['temps']:
        print(f'  CPU temp: {snap["temps"].get("cpu", "unknown")}°C')
    print()
    
    # Analyze trends
    history = load_history(days=30)
    analysis = analyze_trends(history)
    
    print(f'Analysis confidence: {analysis["confidence"]} ({analysis["samples"]} samples)')
    print()
    
    if analysis['alerts']:
        print('⚠️  PREDICTIVE ALERTS:')
        for alert in analysis['alerts']:
            print(f'\n  [{alert["severity"]}] {alert["component"]}')
            print(f'    {alert["issue"]}')
            if 'eta_days' in alert:
                print(f'    Estimated: {alert["eta_days"]}')
            if 'suggestion' in alert:
                print(f'    Suggestion: {alert["suggestion"]}')
    else:
        print('✓ No predictive alerts')
    
    print()
    return 0 if not analysis['alerts'] else 1

def status():
    """Quick status check"""
    snap = collect_snapshot()
    
    health_score = 100
    issues = []
    
    if snap['nvme'].get('percentage_used', 0) > 70:
        health_score -= 20
        issues.append('NVMe wear elevated')
    
    if snap['temps'].get('cpu', 0) > 85:
        health_score -= 15
        issues.append('CPU temp high')
    
    print(f'health_score={health_score}')
    if issues:
        print(f'issues={issues}')
    
    return 0 if health_score > 80 else 1

def main():
    parser = argparse.ArgumentParser(description='Predictive hardware failure detection')
    sub = parser.add_subparsers(dest='cmd')
    
    sub.add_parser('predict', help='run prediction analysis')
    sub.add_parser('status', help='quick health status')
    sub.add_parser('collect', help='collect snapshot only')
    
    args = parser.parse_args()
    
    if args.cmd == 'predict':
        return predict()
    elif args.cmd == 'status':
        return status()
    elif args.cmd == 'collect':
        snap = collect_snapshot()
        save_history(snap)
        print('snapshot collected')
        return 0
    else:
        parser.print_help()
        return 1

if __name__ == '__main__':
    exit(main())
