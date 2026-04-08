#!/usr/bin/env python3
"""
Edge书签API控制器 - HTTP polling 模式
扩展通过 HTTP polling 取命令，返回结果。支持 REST API。
"""

import json, threading, time, uuid, subprocess, signal, socket, struct, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

class ThreadingHTTP(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        # bind_and_activate=False prevents super from creating a separate socket
        kwargs['bind_and_activate'] = False
        super().__init__(*args, **kwargs)
        # Set SO_REUSEADDR on the socket super already created, then bind
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (OSError, AttributeError):
            pass
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.server_bind()
        self.server_activate()

    def shutdown(self):
        super().shutdown()
        try:
            self.socket.close()
        except:
            pass

PORT = 19877
WAIT_TIMEOUT = 15
WIN_EDGE = '/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'

pending_cmd = None
pending_result = None
result_event = threading.Event()

def reload_extension():
    try:
        subprocess.run(['/mnt/c/Windows/System32/taskkill.exe', '/IM', 'msedge.exe', '/F'],
                       capture_output=True, timeout=5)
        time.sleep(2)
        subprocess.Popen([WIN_EDGE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        return {'success': True, 'message': 'Edge restarted'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path)
        global pending_cmd, pending_result
        if p.path == '/cmd':
            cmd = pending_cmd
            pending_cmd = None
            pending_result = None
            result_event.clear()
            self._json(cmd or {})
        elif p.path == '/result':
            self._json(pending_result or {})
        elif p.path == '/health':
            self._json({'status': 'ok'})
        elif p.path == '/search':
            self._json(self._call('search', {'query': parse_qs(p.query).get('q', [''])[0]}))
        elif p.path == '/tree':
            self._json(self._call('tree', {}))
        elif p.path == '/stats':
            self._json(self._call('stats', {}))
        else:
            self._json({'error': 'not found'}, 404)

    def do_POST(self):
        p = urlparse(self.path)
        n = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(n)) if n else {}
        if p.path == '/result':
            global pending_result
            pending_result = body.get('result', body)
            result_event.set()
            self._json({'ok': True})
        elif p.path == '/reload':
            self._json(reload_extension())
        elif p.path in ('/add', '/update', '/remove', '/move'):
            self._json(self._call(p.path.lstrip('/'), body))
        else:
            self._json({'error': 'not found'}, 404)

    def _call(self, action, data):
        global pending_cmd, pending_result
        cid = str(uuid.uuid4())[:8]
        pending_cmd = {'cmd_id': cid, 'action': action, **data}
        pending_result = None
        result_event.clear()
        if result_event.wait(timeout=WAIT_TIMEOUT):
            return pending_result
        return {'success': False, 'error': f'No extension response ({WAIT_TIMEOUT}s)'}

    def _json(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, *a): pass

if __name__ == '__main__':
    server = ThreadingHTTP(('0.0.0.0', PORT), Handler)
    print(f'Bookmark API on :{PORT}', flush=True)
    server.serve_forever()
