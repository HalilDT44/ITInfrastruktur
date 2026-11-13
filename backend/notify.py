"""Independent alert receiver; alerts remain visible when API/DB fail."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.end_headers();self.wfile.write(b'ready: stdout receiver initialized' if self.path=='/ready' else b'alive')
    def do_POST(self):
        data=self.rfile.read(min(int(self.headers.get('Content-Length','0')),1048576))
        print(json.dumps({'notification':json.loads(data)}),flush=True)
        self.send_response(200);self.end_headers()
ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
