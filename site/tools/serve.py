"""Serve site/public locally with the SAME security headers as production
(_headers), so CSP violations surface during testing. Stdlib only.

Usage: .venv/bin/python site/tools/serve.py   ->  http://127.0.0.1:8421
"""

from __future__ import annotations

import http.server
import os
import sys

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUB = os.path.join(SITE, "public")

HEADERS = {}
with open(os.path.join(PUB, "_headers")) as f:
    section = None
    for line in f:
        if not line.startswith("  ") and line.strip():
            section = line.strip()
        elif line.strip() and section == "/*":
            k, v = line.strip().split(": ", 1)
            HEADERS[k] = v


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=PUB, **kw)

    def end_headers(self):
        for k, v in HEADERS.items():
            self.send_header(k, v)
        super().end_headers()

    def log_message(self, fmt, *args):  # quiet
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8421
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler) as srv:
        print(f"serving {PUB} at http://127.0.0.1:{port} with production headers")
        srv.serve_forever()
