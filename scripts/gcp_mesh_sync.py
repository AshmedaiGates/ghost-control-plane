#!/usr/bin/env python3
import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
BASE = HOME / '.local' / 'share' / 'ghost-control-plane'
MESH_DIR = BASE / 'mesh'
MESH_DIR.mkdir(parents=True, exist_ok=True)
NODES_FILE = MESH_DIR / 'nodes.json'

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()


def ssh_cmd(info, *remote_args, batch=True):
    host = info['host']
    user = info.get('user', HOME.name)
    cmd = ['ssh', '-o', 'ConnectTimeout=6']
    if batch:
        cmd.extend(['-o', 'BatchMode=yes'])

    # Prefer dedicated GCP key if present
    gcp_key = HOME / '.ssh' / 'gcp_vps_key'
    if gcp_key.exists():
        cmd.extend(['-i', str(gcp_key), '-o', 'IdentitiesOnly=yes'])

    cmd.append(f'{user}@{host}')
    cmd.extend(list(remote_args))
    return cmd

def load_nodes():
    if NODES_FILE.exists():
        return json.loads(NODES_FILE.read_text())
    return {}

def save_nodes(nodes):
    NODES_FILE.write_text(json.dumps(nodes, indent=2))

def add_node(name, host, user=None):
    nodes = load_nodes()
    nodes[name] = {
        'host': host,
        'user': user or HOME.name,
        'added': datetime.now().isoformat(),
    }
    save_nodes(nodes)
    print(f'added node: {name} ({host})')

def remove_node(name):
    nodes = load_nodes()
    if name in nodes:
        del nodes[name]
        save_nodes(nodes)
        print(f'removed node: {name}')
    else:
        print(f'node not found: {name}')

def list_nodes():
    nodes = load_nodes()
    if not nodes:
        print('no nodes configured')
        return
    print('mesh nodes:')
    for name, info in nodes.items():
        status = check_node(info)
        print(f'  {name}: {info["host"]} ({status})')

def check_node(info):
    rc, _, _ = run(ssh_cmd(info, 'echo', 'ok', batch=True))
    return 'up' if rc == 0 else 'down'

def sync_command(command, target=None):
    nodes = load_nodes()
    if not nodes:
        print('no nodes configured')
        return 1
    
    if target and target not in nodes:
        print(f'target not found: {target}')
        return 1
    
    targets = {target: nodes[target]} if target else nodes
    
    print(f'syncing command: {command}')
    print(f'targets: {", ".join(targets.keys())}')
    print()
    
    for name, info in targets.items():
        host = info['host']

        print(f'[{name}] {host}...')

        # Check if remote has gcp
        rc, _, _ = run(ssh_cmd(info, 'which', 'gcp', batch=True))
        if rc != 0:
            print(f'  warning: gcp not found on {name}')
            continue

        # Execute command
        rc, out, err = run(ssh_cmd(info, 'gcp', *command.split(), batch=True))
        if rc == 0:
            print(f'  ✓ success')
            if out:
                for ln in out.splitlines()[:5]:
                    print(f'    {ln}')
        else:
            print(f'  ✗ failed: {err[:100]}')
    
    return 0

def propagate_scene(scene_name):
    return sync_command(f'scene {scene_name} --apply')

def propagate_backup():
    return sync_command('backup run --apply')

def mesh_status():
    nodes = load_nodes()
    if not nodes:
        print('no mesh nodes')
        return
    
    print('mesh status:')
    for name, info in nodes.items():
        status = check_node(info)
        host = info['host']

        # Check gcp version
        version = 'unknown'
        if status == 'up':
            rc, out, _ = run(ssh_cmd(info, 'gcp', 'update', 'status', batch=True))
            if rc == 0:
                for ln in out.splitlines():
                    if 'local:' in ln:
                        version = ln.split()[1][:12]
        
        print(f'  {name}: {status} ({host}) gcp@{version}')

parser = argparse.ArgumentParser(description='Ghost mesh sync - cross-device control')
sub = parser.add_subparsers(dest='cmd')

p = sub.add_parser('add')
p.add_argument('name')
p.add_argument('host')
p.add_argument('--user')

p = sub.add_parser('remove')
p.add_argument('name')

sub.add_parser('list', help='list mesh nodes')
sub.add_parser('status', help='check mesh status')

p = sub.add_parser('sync')
p.add_argument('command', help='gcp command to sync (e.g. "scene game --apply")')
p.add_argument('--target', help='specific target node')

p = sub.add_parser('scene')
p.add_argument('name', help='scene name to propagate')
p.add_argument('--target')

p = sub.add_parser('backup')
p.add_argument('--target')

args = parser.parse_args()

if args.cmd == 'add':
    add_node(args.name, args.host, args.user)
elif args.cmd == 'remove':
    remove_node(args.name)
elif args.cmd == 'list':
    list_nodes()
elif args.cmd == 'status':
    mesh_status()
elif args.cmd == 'sync':
    sync_command(args.command, args.target)
elif args.cmd == 'scene':
    propagate_scene(args.name)
elif args.cmd == 'backup':
    propagate_backup()
else:
    parser.print_help()
