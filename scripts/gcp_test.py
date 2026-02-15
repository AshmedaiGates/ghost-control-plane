#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = [
    ('checkpoint list', ['python', str(ROOT / 'scripts' / 'gcp_checkpoint.py'), '--list']),
    ('scene list', ['python', str(ROOT / 'scripts' / 'gcp_scene.py'), '--list']),
    ('guard status', ['python', str(ROOT / 'scripts' / 'gcp_guard.py')]),
    ('soc report', ['python', str(ROOT / 'scripts' / 'gcp_soc.py'), '--report']),
    ('profile status', ['bash', '-c', 'powerprofilesctl get 2>/dev/null || echo performance']),
    ('autopilot status', ['systemctl', '--user', 'is-active', 'gcp-autopilot.timer']),
    ('backup config', ['python', str(ROOT / 'scripts' / 'gcp_backup.py'), 'status']),
    ('audio status', ['python', str(ROOT / 'scripts' / 'gcp_audio.py'), 'status']),
    ('network status', ['python', str(ROOT / 'scripts' / 'gcp_network.py'), 'status']),
    ('qos status', ['python', str(ROOT / 'scripts' / 'gcp_qos.py'), 'status']),
    ('cache status', ['python', str(ROOT / 'scripts' / 'gcp_cache.py'), 'status']),
    ('dashboard dry-run', ['python', str(ROOT / 'scripts' / 'gcp_dashboard.py')]),
    ('cognition detect', ['python', str(ROOT / 'scripts' / 'gcp_cognition.py'), 'detect']),
]

def run_test(name, cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode == 0:
        print(f'✓ {name}')
        return True
    else:
        print(f'✗ {name}')
        if p.stderr:
            print(f'  {p.stderr[:100]}')
        return False

def main():
    print('== GCP Integration Test Suite ==')
    print()
    
    passed = 0
    failed = 0
    
    for name, cmd in TESTS:
        if run_test(name, cmd):
            passed += 1
        else:
            failed += 1
    
    print()
    print(f'Results: {passed} passed, {failed} failed')
    
    if failed > 0:
        print('\nSome tests failed. Check individual components.')
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
