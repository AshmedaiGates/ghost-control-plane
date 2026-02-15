#!/usr/bin/env python3
"""
Ghost Control Plane - Workload Planner
Decide what runs where based on specs
"""
import argparse
import json
from pathlib import Path

# Recommended workload distribution
WORKLOADS = {
    'laptop': {
        'name': 'Local Laptop (Legion)',
        'specs': 'RTX 3070, 16GB RAM, CachyOS',
        'best_for': [
            'GPU inference (local LLMs)',
            'Development work',
            'Gaming scene',
            'Heavy compilation (ccache/sccache)',
            'Audio/video editing',
        ],
        'services': [
            'gcp-autopilot.timer (performance tuning)',
            'gcp-snapshot.timer (local state)',
            'gcp-selfheal.timer (self-healing)',
        ],
    },
    'vps_small': {
        'name': 'Small VPS (4GB RAM)',
        'specs': '$15-20/mo, 2-4 cores',
        'best_for': [
            'Mesh coordination node',
            'DNS-over-HTTPS relay',
            'Lightweight CI/CD runner',
            'SSH jump host',
            'Uptime monitoring',
        ],
        'services': [
            'gcp-collab.service (clipboard sync)',
            'gcp-soc-report.timer (security monitoring)',
        ],
    },
    'vps_medium': {
        'name': 'Medium VPS (16GB RAM)',
        'specs': '$40-50/mo, 4-8 cores',
        'best_for': [
            'CI/CD primary runner',
            'CPU-based LLM inference (7B models)',
            'Backup target',
            'Distributed storage node',
            'Secondary mesh hub',
        ],
        'services': [
            'gcp-collab.service',
            'gcp-mesh-ops.timer',
            'gcp-backup.timer',
            'ollama (optional, 7B models)',
        ],
    },
    'vps_large': {
        'name': 'Large VPS (34GB RAM) - YOUR SETUP',
        'specs': '$51/mo, 17 cores, 680GB SSD',
        'best_for': [
            'Primary CI/CD runner',
            'CPU-based LLM inference (13B-24B models)',
            'Main backup target',
            'Primary distributed storage',
            'Always-on mesh hub',
            'Off-site checkpoint storage',
            'Remote development environment',
        ],
        'services': [
            'gcp-collab.service',
            'gcp-mesh-ops.timer',
            'gcp-backup.timer (centralized)',
            'gcp-soc-report.timer',
            'ollama (13B-24B models)',
            'code-server (remote dev)',
        ],
    },
}

def recommend(specs):
    """Recommend workload distribution based on specs"""
    ram_gb = specs.get('ram_gb', 0)
    has_gpu = specs.get('has_gpu', False)
    
    print("=== GCP Workload Distribution ===")
    print()
    
    # Always run on laptop
    print("KEEP ON LAPTOP:")
    for item in WORKLOADS['laptop']['best_for']:
        print(f"  • {item}")
    print()
    
    # Recommend VPS tier
    if ram_gb >= 32:
        tier = 'vps_large'
    elif ram_gb >= 16:
        tier = 'vps_medium'
    else:
        tier = 'vps_small'
    
    vps = WORKLOADS[tier]
    print(f"MOVE TO VPS ({vps['name']}):")
    for item in vps['best_for']:
        print(f"  • {item}")
    print()
    
    print("RECOMMENDED VPS SERVICES:")
    for svc in vps['services']:
        print(f"  • {svc}")
    print()
    
    # Specific recommendations for 34GB setup
    if ram_gb >= 32:
        print("SPECIAL FOR YOUR 34GB SETUP:")
        print("  • Run ollama with 24B models (needs ~20GB RAM)")
        print("  • Use as primary backup target (680GB storage)")
        print("  • Centralized checkpoint storage for laptop")
        print("  • Remote dev environment when laptop unavailable")
        print()
        print("COST-BENEFIT:")
        print("  • $51/mo for 34GB is $1.50/GB - excellent value")
        print("  • Equivalent GPU VPS: $300-600/mo (you save $250-550)")
        print("  • Offloads CI/builds from laptop = longer laptop life")
        print()

def compare_gpu_vps():
    """Compare CPU vs GPU VPS costs"""
    print("=== GPU VPS Reality Check ===")
    print()
    print("GPU VPS Options (24GB VRAM for quality LLMs):")
    print("  • TensorDock RTX 4090: ~$255/mo")
    print("  • Lambda Cloud A10: ~$600/mo")
    print("  • Vultr Cloud GPU: ~$720/mo")
    print("  • Your laptop RTX 3070: $0 (already paid)")
    print()
    print("Your $51 34GB CPU VPS Strategy:")
    print("  • Run 13B models fast (RAM is cheaper than VRAM)")
    print("  • Use API for heavy inference when needed")
    print("  • Local RTX 3070 for 24/7 GPU inference")
    print("  • Total cost: $51/mo vs $300-600/mo for GPU VPS")
    print("  • Savings: $250-550/mo")
    print()

def main():
    parser = argparse.ArgumentParser(description='GCP workload planner')
    parser.add_argument('--ram', type=int, default=34, help='VPS RAM in GB')
    parser.add_argument('--gpu', action='store_true', help='VPS has GPU')
    parser.add_argument('--compare', action='store_true', help='Compare GPU VPS costs')
    
    args = parser.parse_args()
    
    if args.compare:
        compare_gpu_vps()
    else:
        specs = {'ram_gb': args.ram, 'has_gpu': args.gpu}
        recommend(specs)

if __name__ == '__main__':
    main()
