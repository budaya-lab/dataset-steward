#!/usr/bin/env python3
"""Local viewer and editor for ds-* datasets.

    python server.py                    datasets next to _describe/, port 8765
    python server.py --input /data --port 9000

Validates every ds-* folder on startup and recounts each resource's size, which
updates datapackage.json. Listens on localhost only. Saving edits datapackage.json
and, if the dataset passes, its README. It never touches git.
Needs the `markdown` package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    import markdown
except ImportError:
    sys.exit("server.py needs the markdown package: pip install markdown")

import validate

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src https: data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
MAX_BODY = 5 * 1024 * 1024
FOLDER_RE = re.compile(r"^ds-[^/\\]+$")
CHART_TOKEN = "BUCKETSCHARTPLACEHOLDER"
KEY_ORDER = (
    "$schema", "name", "title", "description", "keywords", "created", "contributors", "resources", "sources",
)
SAVE_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def render_markdown(text: str) -> str:
    """Render markdown with raw HTML shown as text, since READMEs and metadata are data."""
    renderer = markdown.Markdown(extensions=["tables", "fenced_code"])
    renderer.preprocessors.deregister("html_block")
    renderer.inlinePatterns.deregister("html")
    return renderer.convert(text)


def etag_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def ordered_package(package: dict) -> dict:
    ordered = {key: package[key] for key in KEY_ORDER if key in package}
    ordered.update((key, value) for key, value in package.items() if key not in ordered)
    return ordered


class App:
    def __init__(self, input_dir: Path):
        self.input_dir = Path(input_dir).resolve()
        self.rules = validate.load_rules()

    def folder(self, name: str) -> Path:
        path = self.input_dir / name
        if not FOLDER_RE.match(name) or not path.is_dir():
            raise ApiError(HTTPStatus.NOT_FOUND, f"No dataset named {name!r}")
        return path

    def summary(self, report: validate.Report, folder: Path) -> dict:
        package, _ = validate.load_package(folder)
        title = (package or {}).get("title")
        return {
            "folder": report.folder,
            "title": title if isinstance(title, str) else "",
            "ok": report.ok,
            "errors": len(report.errors),
            "warnings": len(report.warnings),
        }

    def list(self) -> list[dict]:
        return [
            self.summary(validate.validate_folder(folder, self.rules), folder)
            for folder in validate.discover(self.input_dir)
        ]

    def revalidate(self) -> list[validate.Report]:
        return [validate.process_folder(f, self.rules) for f in validate.discover(self.input_dir)]

    def detail(self, name: str) -> dict:
        folder = self.folder(name)
        path = folder / validate.DATAPACKAGE
        report = validate.validate_folder(folder, self.rules)
        package, problem = validate.load_package(folder)
        buckets = validate.read_buckets(folder / validate.BUCKETS)

        readme = validate.readme_path(folder)
        existing = readme.read_text(encoding="utf-8") if readme.is_file() else ""
        notes = validate.extract_notes(existing)
        sized = validate.with_sizes(package, folder) if package else package
        body = validate.render_body(sized, buckets, name, buckets_block=CHART_TOKEN)
        html = render_markdown(body).replace(f"<p>{CHART_TOKEN}</p>", '<div id="buckets-chart"></div>', 1)
        if notes:
            html += '<hr class="notes-rule">' + render_markdown(notes)

        return {
            "folder": name,
            "report": report.to_dict(),
            "etag": etag_of(path),
            "raw": path.read_text(encoding="utf-8") if path.is_file() else "",
            "package": sized,
            "package_problem": problem,
            "stages": self.rules["stages"],
            "stubs": validate.stub_resources(folder, report.undescribed, package),
            "readme_html": html,
            "readme_current": readme.is_file() and existing == validate.expected_readme(folder),
            "readme_name": readme.name,
            "charts": validate.bucket_charts(buckets),
            "bucket_table": {"headers": buckets["headers"], "rows": buckets["rows"]},
            "buckets_present": buckets["present"],
        }

    def save(self, name: str, body: dict) -> dict:
        folder = self.folder(name)
        path = folder / validate.DATAPACKAGE
        if isinstance(body.get("raw"), str):
            text = body["raw"]
            try:
                package = json.loads(text)
            except ValueError as exc:
                raise ApiError(HTTPStatus.BAD_REQUEST, f"Not valid JSON: {exc}")
            if not isinstance(package, dict):
                raise ApiError(HTTPStatus.BAD_REQUEST, "datapackage.json must be a JSON object")
            text = text.rstrip() + "\n"
        elif isinstance(body.get("package"), dict):
            package = ordered_package(body["package"])
            if package.get("sources") == []:  # the form always carries the list
                del package["sources"]
            text = json.dumps(package, indent=2, ensure_ascii=False) + "\n"
        else:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Expected package or raw")

        with SAVE_LOCK:
            if body.get("etag") != etag_of(path):
                raise ApiError(
                    HTTPStatus.CONFLICT,
                    "datapackage.json changed on disk since you opened it. Copy your edits, reload and try again.",
                )
            validate.write_atomic(path, text)
            report = validate.process_folder(folder, self.rules)

        detail = self.detail(name)
        detail["report"]["readme_written"] = report.readme_written
        return detail


class Handler(BaseHTTPRequestHandler):
    app: App
    server_version = "describe"

    def log_message(self, format, *args):  # noqa: A002 - signature set by the base class
        pass

    def _allowed_origin(self) -> bool:
        # Stops other websites, and DNS rebinding, from driving the local API.
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed:
            return False
        origin = self.headers.get("Origin")
        return origin is None or urlsplit(origin).netloc in allowed

    def _send(self, status: HTTPStatus, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        if self.headers.get_content_type() != "application/json":
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Expected application/json")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise ApiError(HTTPStatus.LENGTH_REQUIRED, "Content-Length required")
        if length > MAX_BODY:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request too large")
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Request body is not JSON")
        if not isinstance(body, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Expected a JSON object")
        return body

    def _dispatch(self, method: str) -> None:
        if not self._allowed_origin():
            self._json({"error": "Forbidden origin"}, HTTPStatus.FORBIDDEN)
            return
        path = urlsplit(self.path).path
        try:
            if method == "GET" and path in STATIC_FILES:
                filename, content_type = STATIC_FILES[path]
                self._send(HTTPStatus.OK, (STATIC_DIR / filename).read_bytes(), content_type)
                return
            if method == "GET" and path == "/api/datasets":
                self._json(self.app.list())
                return
            if method == "POST" and path == "/api/revalidate":
                self._read_json()
                written = [r.folder for r in self.app.revalidate() if r.readme_written]
                self._json({"datasets": self.app.list(), "readmes_written": written})
                return
            match = re.fullmatch(r"/api/datasets/([^/]+)", path)
            if match:
                name = unquote(match.group(1))
                if method == "GET":
                    self._json(self.app.detail(name))
                    return
                if method == "PUT":
                    self._json(self.app.save(name, self._read_json()))
                    return
            raise ApiError(HTTPStatus.NOT_FOUND, "Not found")
        except ApiError as exc:
            self._json({"error": exc.message}, exc.status)
        except OSError as exc:
            self._json({"error": f"Could not read or write a file: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self):  # noqa: N802 - name set by the base class
        self._dispatch("GET")

    def do_PUT(self):  # noqa: N802
        self._dispatch("PUT")

    def do_POST(self):  # noqa: N802
        self._dispatch("POST")


def make_server(input_dir: Path, port: int) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"app": App(input_dir)})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="View and edit ds-* dataset metadata.")
    parser.add_argument("--input", type=Path, default=validate.HERE.parent, help="folder holding the ds-* folders")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if not args.input.is_dir():
        parser.error(f"not a folder: {args.input}")
    server = make_server(args.input, args.port)
    reports = server.RequestHandlerClass.app.revalidate()
    print("\n\n".join(validate.format_report(r) for r in reports) or f"No ds-* folders in {args.input}")
    print(f"\n{sum(r.ok for r in reports)} of {len(reports)} datasets pass")
    print(f"Viewer: http://127.0.0.1:{server.server_address[1]}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
