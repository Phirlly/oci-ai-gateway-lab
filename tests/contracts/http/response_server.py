"""Finite loopback responses for testing whole-request time limits."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread


class ResponseHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def drip(self, fragment):
        for _ in range(40):
            if self.server.stop.wait(0.05):
                return
            self.wfile.write(fragment)
            self.wfile.flush()

    def do_GET(self):
        try:
            if self.path == "/slow-headers":
                self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Delay: ")
                self.drip(b".")
                self.wfile.write(b"\r\nContent-Length: 2\r\n\r\nOK")
            elif self.path == "/slow-body":
                self.send_response(200)
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.drip(b"c\r\ndata: ping\n\n\r\n")
                self.wfile.write(b"0\r\n\r\n")
            else:
                body = b'{"ok": true}'
                self.send_response(403 if self.path == "/denied" else 200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Expected when a timed-out client closes its socket.


@contextmanager
def response_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ResponseHandler)
    server.daemon_threads = False
    server.stop = Event()
    worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    worker.start()
    try:
        yield "http://127.0.0.1:" + str(server.server_port)
    finally:
        server.stop.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
        if worker.is_alive():
            raise RuntimeError("HTTP fixture serving thread did not stop")
