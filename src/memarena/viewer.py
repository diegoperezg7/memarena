"""Serve the bundled viewer locally, or export it as a static site (e.g. for GitHub Pages)."""

from __future__ import annotations

import http.server
import json
import shutil
import socketserver
import threading
import webbrowser
from functools import partial
from importlib import resources
from pathlib import Path

from .errors import MemarenaError
from .models import QuestionSet


def dist_dir() -> Path:
    d = Path(str(resources.files("memarena") / "viewer_dist"))
    if not (d / "index.html").exists():
        raise MemarenaError(
            "The viewer is not built. From a source checkout run: cd viewer && npm ci && npm run build"
        )
    return d


def export_site(out: Path, results: Path | None, questions: Path | None, history: Path | None = None) -> Path:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(dist_dir(), out)
    data = out / "data"
    data.mkdir(exist_ok=True)
    manifest = {}
    if results:
        shutil.copy(results, data / "results.json")
        manifest["results"] = "data/results.json"
    if questions:
        shutil.copy(questions, data / "questions.json")
        manifest["questions"] = "data/questions.json"
    if history:
        shutil.copy(history, data / "history.json")
        manifest["history"] = "data/history.json"
    (data / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return out


class _Handler(http.server.SimpleHTTPRequestHandler):
    questions_path: Path | None = None

    def log_message(self, *args):  # keep the terminal quiet
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?")[0] == "/api/ping":
            body = json.dumps({"editable": self.questions_path is not None}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/data/questions.json" and self.questions_path is not None:
            body = self.questions_path.read_bytes()  # always the live file, so saved edits show up
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_PUT(self):
        if self.path != "/api/questions" or self.questions_path is None:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if length > 20_000_000:
            self.send_error(413)
            return
        try:
            data = json.loads(self.rfile.read(length))
            qs = QuestionSet.from_json(data)  # validates shape before overwriting the file
        except (ValueError, TypeError, KeyError) as e:
            self.send_error(400, str(e)[:100])
            return
        qs.save(self.questions_path)
        self.send_response(204)
        self.end_headers()


def serve(
    site: Path, port: int = 8765, open_browser: bool = True, questions_path: Path | None = None
) -> None:
    handler = type("Handler", (_Handler,), {"questions_path": questions_path})
    socketserver.TCPServer.allow_reuse_address = True
    try:
        httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), partial(handler, directory=str(site)))
    except OSError as e:
        raise MemarenaError(f"Port {port} is busy. Pick another with --port.") from e
    url = f"http://127.0.0.1:{port}/"
    print(f"Viewer running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
