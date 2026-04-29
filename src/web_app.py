"""Local web UI for deterministic futures analysis and optional agent chat."""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .agent import run_analysis
from .data_loader import load_csv


ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "web"
DEFAULT_DATA_PATH = ROOT_DIR / "data" / "sample_futures_data.csv"


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _safe_static_path(request_path: str) -> Path | None:
    relative = request_path.lstrip("/") or "index.html"
    candidate = (STATIC_DIR / relative).resolve()
    try:
        candidate.relative_to(STATIC_DIR.resolve())
    except ValueError:
        return None
    return candidate


class FuturesWebHandler(BaseHTTPRequestHandler):
    agent_instance = None
    agent_error = None
    data_path = DEFAULT_DATA_PATH

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/health":
            _json_response(
                self,
                {
                    "ok": True,
                    "data_path": str(self.data_path),
                    "agent_available": self.agent_instance is not None,
                    "agent_error": self.agent_error,
                },
            )
            return

        if parsed.path == "/api/market-data":
            self._handle_market_data()
            return

        if parsed.path == "/api/analyze":
            self._handle_analyze(parsed.query)
            return

        if parsed.path == "/":
            self._serve_static("/index.html")
            return

        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/chat":
            self._handle_chat()
            return

        _json_response(self, {"error": "Not found."}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:
        return

    def _serve_static(self, request_path: str) -> None:
        file_path = _safe_static_path(request_path)
        if file_path is None or not file_path.exists() or not file_path.is_file():
            _json_response(self, {"error": "Not found."}, status=HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(str(file_path))
        payload = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_market_data(self) -> None:
        try:
            dataframe = load_csv(self.data_path)
        except Exception as exc:
            _json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        rows = []
        for _, row in dataframe.tail(60).iterrows():
            rows.append(
                {
                    "datetime": row["datetime"].isoformat(),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                }
            )

        _json_response(
            self,
            {
                "rows": rows,
                "row_count": len(dataframe),
                "latest_timestamp": dataframe.iloc[-1]["datetime"].isoformat(),
            },
        )

    def _handle_analyze(self, query: str) -> None:
        params = parse_qs(query)
        use_vwap_filter = params.get("use_vwap_filter", ["true"])[0].lower() != "false"
        run_historical_backtest = params.get("run_historical_backtest", ["false"])[0].lower() == "true"
        stop_offset = float(params.get("stop_offset", ["1.0"])[0])
        reward_multiple = float(params.get("reward_multiple", ["2.0"])[0])

        try:
            result = run_analysis(
                self.data_path,
                use_vwap_filter=use_vwap_filter,
                run_historical_backtest=run_historical_backtest,
                stop_offset=stop_offset,
                reward_multiple=reward_multiple,
            )
        except Exception as exc:
            _json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        _json_response(self, result)

    def _handle_chat(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            _json_response(self, {"error": "Request body must be valid JSON."}, status=HTTPStatus.BAD_REQUEST)
            return

        prompt = str(body.get("prompt", "")).strip()
        if not prompt:
            _json_response(self, {"error": "Prompt is required."}, status=HTTPStatus.BAD_REQUEST)
            return

        if self.agent_instance is None:
            _json_response(
                self,
                {
                    "error": "Agent chat is unavailable in this environment.",
                    "details": self.agent_error,
                },
                status=HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return

        try:
            answer = self.agent_instance.ask(prompt)
        except Exception as exc:
            _json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
            return

        _json_response(self, {"answer": answer})


def build_handler(data_path: str | Path | None = None):
    class ConfiguredFuturesWebHandler(FuturesWebHandler):
        pass

    ConfiguredFuturesWebHandler.data_path = Path(data_path or DEFAULT_DATA_PATH)

    try:
        from .futures_agent import FuturesAgent
    except Exception as exc:
        ConfiguredFuturesWebHandler.agent_instance = None
        ConfiguredFuturesWebHandler.agent_error = str(exc)
    else:
        try:
            ConfiguredFuturesWebHandler.agent_instance = FuturesAgent(csv_path=ConfiguredFuturesWebHandler.data_path)
            ConfiguredFuturesWebHandler.agent_error = None
        except Exception as exc:
            ConfiguredFuturesWebHandler.agent_instance = None
            ConfiguredFuturesWebHandler.agent_error = str(exc)

    return ConfiguredFuturesWebHandler


def serve(host: str = "127.0.0.1", port: int = 8000, data_path: str | Path | None = None) -> None:
    server = ThreadingHTTPServer((host, port), build_handler(data_path=data_path))
    print(f"Futures web app running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
