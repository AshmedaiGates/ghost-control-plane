#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

HOME = Path.home()
BASE = HOME / '.local' / 'share' / 'ghost-control-plane'
DIST_DIR = BASE / 'distributed'
CHUNKS_DIR = DIST_DIR / 'chunks'
METADATA_DIR = DIST_DIR / 'metadata'
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
METADATA_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()

def derive_key(passphrase, salt):
    """Derive encryption key from passphrase"""
    return hashlib.pbkdf2_hmac('sha256', passphrase.encode(), salt, 100000)

def encrypt_file(input_path, output_path, passphrase):
    """Encrypt file using gpg"""
    # Use gpg for actual encryption
    rc, _, err = run([
        'gpg', '--batch', '--yes', '--passphrase', passphrase,
        '--symmetric', '--cipher-algo', 'AES256',
        '-o', str(output_path), str(input_path)
    ])
    return rc == 0

def decrypt_file(input_path, output_path, passphrase):
    """Decrypt file using gpg"""
    rc, _, err = run([
        'gpg', '--batch', '--yes', '--passphrase', passphrase,
        '-d', '-o', str(output_path), str(input_path)
    ])
    return rc == 0

def split_file(file_path, chunk_size=CHUNK_SIZE):
    """Split file into chunks"""
    chunks = []
    with open(file_path, 'rb') as f:
        chunk_num = 0
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            chunk_hash = hashlib.blake2b(data, digest_size=32).hexdigest()[:16]
            chunks.append({
                'num': chunk_num,
                'hash': chunk_hash,
                'size': len(data),
            })
            chunk_num += 1
    return chunks

def store_file(file_path, name=None, passphrase=None):
    """Store file in distributed storage"""
    file_path = Path(file_path).expanduser()
    if not file_path.exists():
        print(f'file not found: {file_path}')
        return None
    
    name = name or file_path.name
    file_hash = hashlib.blake2b(file_path.read_bytes(), digest_size=32).hexdigest()[:16]
    
    # Generate encryption key if passphrase provided
    if not passphrase:
        passphrase = secrets.token_hex(32)
        print(f'generated passphrase: {passphrase}')
        print('SAVE THIS - you need it to recover the file')
    
    # Encrypt file
    encrypted = DIST_DIR / f'{file_hash}.gpg'
    if not encrypt_file(file_path, encrypted, passphrase):
        print('encryption failed')
        return None
    
    # Split into chunks
    chunks = split_file(encrypted)
    
    # Store chunks
    for i, chunk_info in enumerate(chunks):
        chunk_path = encrypted.with_suffix(f'.chunk{i}')
        if chunk_path.exists():
            chunk_data = chunk_path.read_bytes()
            chunk_file = CHUNKS_DIR / f'{chunk_info["hash"]}.chunk'
            chunk_file.write_bytes(chunk_data)
    
    # Save metadata
    metadata = {
        'name': name,
        'original_path': str(file_path),
        'file_hash': file_hash,
        'encrypted_path': str(encrypted),
        'chunks': chunks,
        'created': subprocess.datetime.now().isoformat(),
    }
    
    meta_file = METADATA_DIR / f'{file_hash}.json'
    meta_file.write_text(json.dumps(metadata, indent=2))
    
    print(f'stored: {name}')
    print(f'  hash: {file_hash}')
    print(f'  chunks: {len(chunks)}')
    print(f'  metadata: {meta_file}')
    
    return file_hash

def retrieve_file(file_hash, output_path, passphrase):
    """Retrieve and decrypt file"""
    meta_file = METADATA_DIR / f'{file_hash}.json'
    if not meta_file.exists():
        print(f'metadata not found: {file_hash}')
        return False
    
    metadata = json.loads(meta_file.read_text())
    encrypted = DIST_DIR / f'{file_hash}.gpg'
    
    if not encrypted.exists():
        print(f'encrypted file not found locally: {file_hash}')
        print('searching on mesh nodes...')
        # Would search mesh nodes here
        return False
    
    # Decrypt
    decrypted = tempfile.NamedTemporaryFile(delete=False)
    decrypted.close()
    
    if not decrypt_file(encrypted, decrypted.name, passphrase):
        print('decryption failed - wrong passphrase?')
        return False
    
    # Move to output
    output_path = Path(output_path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(decrypted.name, output_path)
    
    print(f'retrieved: {output_path}')
    return True

def sync_to_node(node_name, file_hash=None):
    """Sync chunks to remote mesh node"""
    from gcp_mesh_sync import load_nodes
    
    nodes = load_nodes()
    if node_name not in nodes:
        print(f'node not found: {node_name}')
        return
    
    node = nodes[node_name]
    host = node['host']
    user = node.get('user', HOME.name)
    
    if file_hash:
        # Sync specific file
        files = [DIST_DIR / f'{file_hash}.gpg']
    else:
        # Sync all
        files = list(DIST_DIR.glob('*.gpg'))
    
    for f in files:
        print(f'syncing {f.name} to {node_name}...')
        rc, _, err = run([
            'rsync', '-avz', '--progress',
            str(f),
            f'{user}@{host}:~/.local/share/ghost-control-plane/distributed/'
        ])
        if rc == 0:
            print(f'  ✓ synced')
        else:
            print(f'  ✗ failed: {err}')

def list_storage():
    """List stored files"""
    print('distributed storage:')
    for meta_file in sorted(METADATA_DIR.glob('*.json')):
        data = json.loads(meta_file.read_text())
        size_mb = sum(c['size'] for c in data['chunks']) / 1024 / 1024
        print(f"  {data['name']}")
        print(f"    hash: {meta_file.stem}")
        print(f"    size: {size_mb:.1f} MB")
        print(f"    chunks: {len(data['chunks'])}")

def main():
    parser = argparse.ArgumentParser(description='Encrypted distributed storage')
    sub = parser.add_subparsers(dest='cmd')
    
    p = sub.add_parser('store')
    p.add_argument('file')
    p.add_argument('--name')
    p.add_argument('--passphrase')
    
    p = sub.add_parser('retrieve')
    p.add_argument('hash')
    p.add_argument('output')
    p.add_argument('--passphrase', required=True)
    
    p = sub.add_parser('sync')
    p.add_argument('node')
    p.add_argument('--hash')
    
    sub.add_parser('list', help='list stored files')
    
    args = parser.parse_args()
    
    if args.cmd == 'store':
        store_file(args.file, args.name, args.passphrase)
    elif args.cmd == 'retrieve':
        retrieve_file(args.hash, args.output, args.passphrase)
    elif args.cmd == 'sync':
        sync_to_node(args.node, args.hash)
    elif args.cmd == 'list':
        list_storage()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
