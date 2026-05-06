"""Local web UI for deterministic futures analysis and optional agent chat."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .live_data import create_live_data_hub
from .audit_logging import active_log_path, configure_logging, flush_transcript


ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "web"
DEFAULT_DATA_PATH = ROOT_DIR / "data" / "sample_futures_data.csv"
MVP_DATA_PATH = ROOT_DIR / "sample_data.csv"
DEFAULT_DISPLAY_METADATA = {
    "symbol": os.getenv("DISPLAY_SYMBOL", "NQ=F"),
    "timeframe": os.getenv("DISPLAY_TIMEFRAME", "5 minutes"),
    "chart_type": os.getenv("DISPLAY_CHART_TYPE", "Candles"),
    "currency": os.getenv("DISPLAY_CURRENCY", "USD"),
    "tick_size": os.getenv("DISPLAY_TICK_SIZE", "0.25"),
    "point_value": os.getenv("DISPLAY_POINT_VALUE", "20"),
    "precision": os.getenv("DISPLAY_PRECISION", "Default"),
}

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from data_loader import load_candles as load_mvp_candles  # noqa: E402
from llm_explainer import explain_result as explain_mvp_result  # noqa: E402
from strategy import analyze_candles as analyze_mvp_candles  # noqa: E402


log = logging.getLogger("agent")


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _mvp_candles_from_dataframe(dataframe) -> list[dict]:
    candles = []
    for _, row in dataframe.iterrows():
        timestamp = row["datetime"]
        candles.append(
            {
                "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )
    return candles


def _run_mvp_analysis(
    reward_multiple: float = 2.0,
    stop_buffer: float = 1.0,
    dataframe=None,
    data_source: str = "sample_data.csv",
) -> dict:
    if dataframe is None:
        candles = load_mvp_candles(MVP_DATA_PATH)
        data_path = str(MVP_DATA_PATH)
    else:
        candles = _mvp_candles_from_dataframe(dataframe)
        data_path = None

    result = analyze_mvp_candles(
        candles,
        reward_multiple=reward_multiple,
        stop_buffer=stop_buffer,
    )
    log.info(
        "MVP analysis result: source=%s rows=%s setup_found=%s direction=%s confidence=%s",
        data_source,
        len(candles),
        result["setup_found"],
        result["direction"],
        result["confidence_score"],
    )
    rows = [
        {
            "timestamp": row["timestamp"],
            "datetime": row["timestamp"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }
        for row in candles
    ]
    return {
        "data_source": data_source,
        "data_path": data_path,
        "row_count": len(candles),
        "latest_timestamp": candles[-1]["timestamp"],
        "result": result,
        "explanation": explain_mvp_result(result),
        "rows": rows,
    }


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
    live_data_hub = None
    data_source_mode = "yfinance"
    data_source_error = None
    display_metadata = DEFAULT_DISPLAY_METADATA

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/health":
            _json_response(
                self,
                {
                    "ok": True,
                    "data_path": None if self.data_source_mode == "yfinance" else str(self.data_path),
                    "agent_available": self.agent_instance is not None,
                    "agent_error": self.agent_error,
                    "live_data_provider": None if self.live_data_hub is None else self.live_data_hub.provider_name,
                    "data_source": self.data_source_mode,
                    "data_source_error": self.data_source_error,
                    "timeframe_minutes": None if self.live_data_hub is None else self.live_data_hub.snapshot().get("timeframe_minutes"),
                    "display_metadata": self.display_metadata,
                    "active_log_path": active_log_path(),
                },
            )
            return

        if parsed.path == "/api/mvp/analyze":
            self._handle_mvp_analyze(parsed.query)
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
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_mvp_analyze(self, query: str) -> None:
        params = parse_qs(query)
        reward_multiple = float(params.get("reward_multiple", ["2.0"])[0])
        stop_buffer = float(params.get("stop_buffer", ["1.0"])[0])

        try:
            dataframe = None if self.live_data_hub is None else self.live_data_hub.dataframe()
            data_source = "sample_data.csv" if dataframe is None else self.live_data_hub.provider_name
            log.info(
                "MVP analysis requested: source=%s reward_multiple=%s stop_buffer=%s",
                data_source,
                reward_multiple,
                stop_buffer,
            )
            payload = _run_mvp_analysis(
                reward_multiple=reward_multiple,
                stop_buffer=stop_buffer,
                dataframe=dataframe,
                data_source=data_source,
            )
        except Exception as exc:
            log.exception("Guardrail event: MVP analysis failed")
            _json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        flush_transcript()
        _json_response(self, payload)

    def _handle_chat(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            log.warning("Malformed chat request body: %s", raw_body.decode("utf-8", errors="replace"))
            _json_response(self, {"error": "Request body must be valid JSON."}, status=HTTPStatus.BAD_REQUEST)
            return

        prompt = str(body.get("prompt", "")).strip()
        if not prompt:
            log.warning("Guardrail event: empty chat prompt rejected")
            _json_response(self, {"error": "Prompt is required."}, status=HTTPStatus.BAD_REQUEST)
            return

        if self.agent_instance is None:
            log.warning("Guardrail event: chat unavailable: %s", self.agent_error)
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
            session_log_path = self.agent_instance.start_new_session()

            from .futures_tools import FuturesToolbox
            import pandas as pd

            symbol = self.display_metadata.get("symbol", "NQ=F")
            timeframe = self.display_metadata.get("timeframe", "5 minutes")
            live_dataframe = None if self.live_data_hub is None else self.live_data_hub.dataframe()
            data_source = "sample_data.csv" if live_dataframe is None else self.live_data_hub.provider_name
            mvp_payload = _run_mvp_analysis(dataframe=live_dataframe, data_source=data_source)
            setup_context = mvp_payload["result"]
            market_bias_context = {
                "direction": setup_context["direction"],
                "confidence_score": setup_context["confidence_score"],
                "source": "FibAgent MVP deterministic strategy",
            }
            toolbox_dataframe = pd.DataFrame(mvp_payload["rows"]).assign(symbol=symbol, contract=symbol)
            request_toolbox = FuturesToolbox(dataframe=toolbox_dataframe)
            log.info(
                "Chat request: prompt=%s setup_found=%s direction=%s confidence=%s source=%s",
                prompt,
                setup_context["setup_found"],
                setup_context["direction"],
                setup_context["confidence_score"],
                data_source,
            )

            contextual_prompt = (
                "Current FibAgent chart context:\n"
                f"- Default symbol/contract: {symbol}\n"
                f"- Timeframe: {timeframe}\n"
                f"- Data provider: {mvp_payload['data_source']}\n"
                f"- Current deterministic setup state: {json.dumps(setup_context, default=str)}\n"
                f"- Current market bias state: {json.dumps(market_bias_context, default=str)}\n"
                "- If the user omits a symbol or contract, use the default symbol/contract above.\n"
                "- If the user asks whether the market data is bullish or bearish, and does not explicitly ask "
                "for a trade setup, use the current market bias state for the answer.\n"
                "- When answering setup questions, treat the deterministic setup state as authoritative. "
                "Explain in plain English whether a valid setup exists and whether entry, stop, and target "
                "are available. Do not invent trade levels when setup_found is false.\n"
                "- Return JSON only if the user explicitly asks for JSON, structured output, schema output, "
                "or a machine-readable response. If JSON is requested, return exactly these keys: direction, "
                "entry, stop, target, confidence_score. If setup_found is false, use direction \"neutral\" and "
                "null for entry, stop, and target. Do not wrap it in markdown.\n"
                "- For questions about latest price, OHLCV, movement, trend, setup state, or dataset state, "
                "use the available tools or deterministic context instead of asking the user to repeat the symbol.\n\n"
                f"User question: {prompt}"
            )
            answer = self.agent_instance.ask(
                contextual_prompt,
                toolbox=request_toolbox,
                create_session_log=False,
            )
        except Exception as exc:
            log.exception("Guardrail event: chat failed")
            _json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
            return

        log.info("Chat final response: %s", answer)
        flush_transcript()
        _json_response(self, {"answer": answer, "active_log_path": str(session_log_path)})


def build_handler(data_path: str | Path | None = None):
    log_path = configure_logging()
    log.info("Building web handler with audit log: %s", log_path)

    class ConfiguredFuturesWebHandler(FuturesWebHandler):
        pass

    ConfiguredFuturesWebHandler.data_path = Path(data_path or DEFAULT_DATA_PATH)
    ConfiguredFuturesWebHandler.display_metadata = DEFAULT_DISPLAY_METADATA.copy()
    ConfiguredFuturesWebHandler.data_source_mode = "yfinance"
    ConfiguredFuturesWebHandler.data_source_error = None
    previous_provider = os.environ.get("LIVE_DATA_PROVIDER")
    os.environ["LIVE_DATA_PROVIDER"] = "yfinance"
    try:
        ConfiguredFuturesWebHandler.live_data_hub = create_live_data_hub(ConfiguredFuturesWebHandler.data_path)
        log.info("Live data hub started: provider=%s", ConfiguredFuturesWebHandler.live_data_hub.provider_name)
    except Exception as exc:
        ConfiguredFuturesWebHandler.live_data_hub = None
        ConfiguredFuturesWebHandler.data_source_error = str(exc)
        log.exception("Guardrail event: live data hub unavailable")
    finally:
        if previous_provider is None:
            os.environ.pop("LIVE_DATA_PROVIDER", None)
        else:
            os.environ["LIVE_DATA_PROVIDER"] = previous_provider

    try:
        from .futures_agent import FuturesAgent
    except Exception as exc:
        ConfiguredFuturesWebHandler.agent_instance = None
        ConfiguredFuturesWebHandler.agent_error = str(exc)
    else:
        try:
            ConfiguredFuturesWebHandler.agent_instance = FuturesAgent(
                csv_path=ConfiguredFuturesWebHandler.data_path,
                preserve_history=False,
            )
            ConfiguredFuturesWebHandler.agent_error = None
            log.info("Agent available: log=%s", ConfiguredFuturesWebHandler.agent_instance.active_log_path)
        except Exception as exc:
            ConfiguredFuturesWebHandler.agent_instance = None
            ConfiguredFuturesWebHandler.agent_error = str(exc)
            log.exception("Guardrail event: agent initialization failed")

    return ConfiguredFuturesWebHandler


def serve(host: str = "127.0.0.1", port: int = 8000, data_path: str | Path | None = None) -> None:
    server = ThreadingHTTPServer((host, port), build_handler(data_path=data_path))
    log.info("Futures web app running at http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
