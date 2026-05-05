"""Standalone web server for the duplicated FibAgent MVP website."""

from __future__ import annotations

import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
WEB_DIR = ROOT_DIR / "web"
CORE_DIR = ROOT_DIR / "core"
DATA_PATH = CORE_DIR / "sample_data.csv"

sys.path.insert(0, str(CORE_DIR))

from data_loader import load_candles  # noqa: E402
from llm_explainer import explain_result  # noqa: E402
from strategy import analyze_candles  # noqa: E402


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    """Send a JSON response."""
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def safe_static_path(request_path: str) -> Path | None:
    """Prevent requests from escaping the web directory."""
    relative = request_path.lstrip("/") or "index.html"
    candidate = (WEB_DIR / relative).resolve()
    try:
        candidate.relative_to(WEB_DIR.resolve())
    except ValueError:
        return None
    return candidate


def run_mvp_analysis() -> dict:
    """Run the duplicated deterministic MVP strategy."""
    candles = load_candles(DATA_PATH)
    result = analyze_candles(candles)
    return {
        "data_source": "sample_data.csv",
        "row_count": len(candles),
        "latest_timestamp": candles[-1]["timestamp"],
        "result": result,
        "explanation": explain_result(result),
        "rows": candles,
    }


class FibAgentMvpHandler(BaseHTTPRequestHandler):
    """Serve static files and MVP API routes."""

    def do_GET(self) -> None:
        if self.path == "/api/health":
            json_response(self, {"ok": True, "project": "FibAgent MVP", "data_source": str(DATA_PATH)})
            return

        if self.path == "/api/analyze":
            try:
                json_response(self, run_mvp_analysis())
            except Exception as exc:
                json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self.serve_static(self.path)

    def serve_static(self, request_path: str) -> None:
        file_path = safe_static_path(request_path)
        if file_path is None or not file_path.exists() or not file_path.is_file():
            json_response(self, {"error": "Not found."}, status=HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        payload = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:
        return


def serve(host: str = "127.0.0.1", port: int = 8010) -> None:
    server = ThreadingHTTPServer((host, port), FibAgentMvpHandler)
    print(f"FibAgent MVP website running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
