"""Local release server; only synthetic manifests, signatures and executable fixtures."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading


class FakeReleases:
    def __init__(self):
        self.routes, self.seen = {}, []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fake.seen.append((self.path, self.headers.get("Authorization")))
                status, body, headers = fake.routes.get(self.path, (404, b"missing", {}))
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = "http://127.0.0.1:" + str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
