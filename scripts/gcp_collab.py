#!/usr/bin/env python3
import argparse
import json
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

HOME = Path.home()
BASE = HOME / '.local' / 'share' / 'ghost-control-plane'
COLLAB_DIR = BASE / 'collab'
COLLAB_DIR.mkdir(parents=True, exist_ok=True)

COLLAB_PORT = 17472  # "GCP" on phone keypad + some

def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()

def get_mesh_nodes():
    """Load mesh nodes from mesh sync"""
    mesh_file = BASE / 'mesh' / 'nodes.json'
    if mesh_file.exists():
        return json.loads(mesh_file.read_text())
    return {}

class CollabServer:
    """Simple collaboration server for clipboard/session sharing"""
    
    def __init__(self, port=COLLAB_PORT):
        self.port = port
        self.clipboard_file = COLLAB_DIR / 'shared_clipboard'
        self.sessions_file = COLLAB_DIR / 'shared_sessions'
    
    def start(self):
        """Start listening for collaboration requests"""
        print(f'Collaboration server on port {self.port}')
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', self.port))
        sock.listen(5)
        
        try:
            while True:
                conn, addr = sock.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr)).start()
        except KeyboardInterrupt:
            print('\nServer stopped')
    
    def handle_client(self, conn, addr):
        """Handle incoming collaboration request"""
        try:
            data = conn.recv(4096).decode('utf-8')
            msg = json.loads(data)
            
            cmd = msg.get('cmd')
            
            if cmd == 'clipboard_set':
                content = msg.get('content', '')
                self.clipboard_file.write_text(content)
                # Also set local clipboard
                run(['wl-copy'] if self.is_wayland() else ['xclip', '-selection', 'clipboard'], 
                    input=content.encode())
                conn.sendall(json.dumps({'status': 'ok'}).encode())
            
            elif cmd == 'clipboard_get':
                if self.clipboard_file.exists():
                    content = self.clipboard_file.read_text()
                else:
                    # Get local clipboard
                    rc, content, _ = run(['wl-paste'] if self.is_wayland() else ['xclip', '-o', '-selection', 'clipboard'])
                conn.sendall(json.dumps({'content': content}).encode())
            
            elif cmd == 'session_share':
                # Share tmux session info
                session_name = msg.get('session', 'shared')
                rc, out, _ = run(['tmux', 'list-sessions'])
                conn.sendall(json.dumps({'sessions': out}).encode())
            
            elif cmd == 'session_attach':
                session_name = msg.get('session', 'shared')
                # Return command to attach
                conn.sendall(json.dumps({
                    'attach_cmd': f'tmux attach -t {session_name}'
                }).encode())
            
            elif cmd == 'code_pointer':
                # Share code location (file:line)
                file_path = msg.get('file')
                line = msg.get('line', 1)
                self.sessions_file.write_text(json.dumps({
                    'file': file_path,
                    'line': line,
                    'timestamp': time.time(),
                }))
                conn.sendall(json.dumps({'status': 'ok'}).encode())
            
            else:
                conn.sendall(json.dumps({'error': 'unknown command'}).encode())
        
        except Exception as e:
            conn.sendall(json.dumps({'error': str(e)}).encode())
        finally:
            conn.close()
    
    def is_wayland(self):
        return 'WAYLAND_DISPLAY' in subprocess.os.environ

class CollabClient:
    """Client for connecting to collaboration server"""
    
    def __init__(self, host, port=COLLAB_PORT):
        self.host = host
        self.port = port
    
    def send(self, msg):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect((self.host, self.port))
            sock.sendall(json.dumps(msg).encode())
            response = sock.recv(4096).decode('utf-8')
            return json.loads(response)
        finally:
            sock.close()
    
    def clipboard_set(self, content):
        return self.send({'cmd': 'clipboard_set', 'content': content})
    
    def clipboard_get(self):
        return self.send({'cmd': 'clipboard_get'})
    
    def share_session(self, session_name='shared'):
        return self.send({'cmd': 'session_share', 'session': session_name})
    
    def code_pointer(self, file_path, line=1):
        return self.send({'cmd': 'code_pointer', 'file': file_path, 'line': line})

def server_start():
    server = CollabServer()
    server.start()

def clipboard_sync(target):
    """Sync clipboard with target device"""
    client = CollabClient(target)
    
    # Get local clipboard
    rc, content, _ = run(['wl-paste'] if 'WAYLAND_DISPLAY' in subprocess.os.environ 
                          else ['xclip', '-o', '-selection', 'clipboard'])
    
    if rc == 0 and content:
        result = client.clipboard_set(content)
        if result.get('status') == 'ok':
            print(f'clipboard synced to {target}')
        else:
            print(f'failed: {result}')
    else:
        print('no clipboard content')

def clipboard_receive(target):
    """Receive clipboard from target device"""
    client = CollabClient(target)
    result = client.clipboard_get()
    content = result.get('content', '')
    
    if content:
        # Set local clipboard
        run(['wl-copy'] if 'WAYLAND_DISPLAY' in subprocess.os.environ 
            else ['xclip', '-selection', 'clipboard'], input=content.encode())
        print(f'clipboard received from {target}')
        print(content[:200])
    else:
        print('no clipboard content from target')

def share_tmux_session(target, session_name='shared'):
    """Share tmux session with target"""
    # Create shared session if not exists
    rc, _, _ = run(['tmux', 'has-session', '-t', session_name])
    if rc != 0:
        run(['tmux', 'new-session', '-d', '-s', session_name])
    
    client = CollabClient(target)
    result = client.share_session(session_name)
    print(f'session shared: {result}')

def code_pointer(target, file_path, line=1):
    """Send code pointer to target"""
    client = CollabClient(target)
    result = client.code_pointer(file_path, line)
    if result.get('status') == 'ok':
        print(f'code pointer sent: {file_path}:{line}')
    else:
        print(f'failed: {result}')

def list_collab_peers():
    """List known collaboration peers"""
    nodes = get_mesh_nodes()
    print('collaboration peers (from mesh):')
    for name, info in nodes.items():
        host = info.get('host', 'unknown')
        print(f'  {name}: {host}:{COLLAB_PORT}')
        # Quick ping
        client = CollabClient(host)
        try:
            result = client.clipboard_get()
            print(f'    status: online')
        except:
            print(f'    status: offline')

def main():
    parser = argparse.ArgumentParser(description='Real-time mesh collaboration')
    sub = parser.add_subparsers(dest='cmd')
    
    sub.add_parser('server', help='start collaboration server')
    
    p = sub.add_parser('clip-send')
    p.add_argument('target', help='target node name or IP')
    
    p = sub.add_parser('clip-recv')
    p.add_argument('target', help='target node name or IP')
    
    p = sub.add_parser('tmux-share')
    p.add_argument('target')
    p.add_argument('--session', default='shared')
    
    p = sub.add_parser('code')
    p.add_argument('target')
    p.add_argument('file')
    p.add_argument('--line', type=int, default=1)
    
    sub.add_parser('peers', help='list collaboration peers')
    
    args = parser.parse_args()
    
    if args.cmd == 'server':
        server_start()
    elif args.cmd == 'clip-send':
        clipboard_sync(args.target)
    elif args.cmd == 'clip-recv':
        clipboard_receive(args.target)
    elif args.cmd == 'tmux-share':
        share_tmux_session(args.target, args.session)
    elif args.cmd == 'code':
        code_pointer(args.target, args.file, args.line)
    elif args.cmd == 'peers':
        list_collab_peers()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
