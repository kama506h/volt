"""Run with python -m volt."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .collector import Collector

STATIC = Path(__file__).parent / 'static'
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.css': ('app.css', 'text/css; charset=utf-8'),
          '/app.js': ('app.js', 'application/javascript; charset=utf-8')}


def handler_for(collector):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Restrict Host to loopback names to resist DNS rebinding.
            host = self.headers.get('Host', '').split(':')[0].lower()
            if host not in ('127.0.0.1', 'localhost'):
                self.send_error(403)
                return
            path = urlsplit(self.path).path
            if path == '/api/stats':
                body = json.dumps(collector.snapshot(), allow_nan=False).encode()
                mime = 'application/json'
            elif path in ASSETS:
                name, mime = ASSETS[path]
                body = (STATIC / name).read_bytes()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description='VOLT: local PC monitor')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    collector = Collector()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(collector))
    collector.start()
    print(f'VOLT → http://127.0.0.1:{server.server_port}  |  Ctrl+C to stop', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        collector.stop.set()
        server.server_close()
        collector.thread.join(timeout=3)


if __name__ == '__main__':
    main()
