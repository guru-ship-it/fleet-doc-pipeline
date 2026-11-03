"""Serve the dashboard on this machine against local records, through the same handler the Lambda runs.

    python demo/rehearse.py                  # writes local_data/rehearsal (records and files)
    python dashboard/serve_local.py 8098     # then open http://localhost:8098  (access code: demo)

Environment: LOCAL_DATA_DIR (default local_data/rehearsal), DASHBOARD_KEY (default demo), REGISTRY_FILE."""
import base64
import os
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("LOCAL_DATA_DIR", "local_data/rehearsal")
os.environ.setdefault("DASHBOARD_KEY", "demo")
os.environ.setdefault("REGISTRY_FILE", "demo/registry.example.json")

from pipeline.dashboard import handle  # noqa: E402  (after the path and environment are set)


UNLOCK = ("<!doctype html><meta charset='utf-8'><script>var q=new URLSearchParams(location.search);"
          "try{sessionStorage.setItem('fleet_demo_code',q.get('code')||'demo')}catch(e){}"
          "location.replace('/'+(q.get('to')||''))</script>")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/_local_unlock"):   # development only: lets a headless browser take screenshots
            body = UNLOCK.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        r = handle("GET", self.path.split("?")[0], dict(self.headers))
        body = base64.b64decode(r["body"]) if r["isBase64Encoded"] else r["body"].encode("utf-8")
        self.send_response(r["statusCode"])
        for k, v in r["headers"].items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):   # one quiet line per request, no headers
        sys.stderr.write("%s %s\n" % (self.command, self.path))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8098
    print("dashboard on http://localhost:%d  (records: %s)" % (port, os.environ["LOCAL_DATA_DIR"]))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
