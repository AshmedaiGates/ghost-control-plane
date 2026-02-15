#!/usr/bin/env python3
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = int(os.getenv('GCP_ANDROID_PORT', '8080'))
TOKEN = os.getenv('GCP_ANDROID_TOKEN', '')
ROOT = Path(__file__).resolve().parent.parent
DASH = Path.home() / '.local' / 'share' / 'ghost-control-plane' / 'android' / 'mobile-dashboard.html'

ALLOWED = {
    'status',
    'dashboard',
    'scene game --apply',
    'scene code --apply',
    'scene focus --apply',
    'scene travel --apply',
    'battle network-reset',
    'battle emergency-perf',
    'backup run --apply',
}


def run_cmd(cmd: str):
    p = subprocess.run(['bash', '-lc', f'~/.local/bin/gcp {cmd}'], capture_output=True, text=True)
    out = (p.stdout or '').strip()
    err = (p.stderr or '').strip()
    return p.returncode, out, err


class H(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _ok(self):
        if not TOKEN:
            return True
        q = parse_qs(urlparse(self.path).query)
        t = q.get('token', [''])[0]
        return t == TOKEN

    def do_GET(self):
        if self.path.startswith('/api/health'):
            if not self._ok():
                return self._json(401, {'error': 'unauthorized'})
            rc, out, err = run_cmd('status')
            return self._json(200 if rc == 0 else 500, {'rc': rc, 'output': out or err})

        # serve dashboard
        if self.path == '/' or self.path.startswith('/mobile-dashboard.html'):
            if not DASH.exists():
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'mobile-dashboard.html missing; run gcp android dashboard')
                return
            html = DASH.read_text()
            # append token helper script
            html += """
<script>
const token = new URLSearchParams(location.search).get('token') || localStorage.getItem('gcp_token') || '';
if (token) localStorage.setItem('gcp_token', token);
const oldFetch = window.fetch;
window.fetch = (u, o={}) => {
  if (typeof u === 'string' && (u.startsWith('/api/'))) {
    u += (u.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token);
  }
  return oldFetch(u, o);
};
</script>
"""
            data = html.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path.startswith('/api/run'):
            if not self._ok():
                return self._json(401, {'error': 'unauthorized'})
            n = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(n).decode() if n else '{}'
            try:
                data = json.loads(body)
            except Exception:
                return self._json(400, {'error': 'bad json'})
            cmd = (data.get('cmd') or '').strip()
            if cmd not in ALLOWED:
                return self._json(403, {'error': 'command not allowed'})
            rc, out, err = run_cmd(cmd)
            return self._json(200 if rc == 0 else 500, {'rc': rc, 'output': out or err})

        self.send_response(404)
        self.end_headers()


if __name__ == '__main__':
    HTTPServer(('0.0.0.0', PORT), H).serve_forever()
