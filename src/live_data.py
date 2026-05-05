"""Live bar streaming primitives for the local futures web app."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .data_loader import load_csv


class LiveDataError(Exception):
    """Raised when the live data provider cannot start or stream safely."""


class CsvReplayProvider:
    """Replay a local CSV row-by-row to simulate a live feed."""

    provider_name = "csv_replay"
    emits_partial_bars = False

    def __init__(self, csv_path: str | Path, loop: bool = True):
        self.csv_path = Path(csv_path)
        self.loop = loop
        self._dataframe = load_csv(self.csv_path)
        if self._dataframe.empty:
            raise LiveDataError(f"No rows available for replay: {self.csv_path}")

    def dataframe(self) -> pd.DataFrame:
        return self._dataframe.copy()

    def iter_bars(self):
        while True:
            for _, row in self._dataframe.iterrows():
                yield row
            if not self.loop:
                return


class DatabentoProvider:
    """Databento-backed futures provider using 1-minute OHLCV resampled to 5 minutes."""

    provider_name = "databento"
    emits_partial_bars = True

    def __init__(
        self,
        api_key: str,
        dataset: str = "GLBX.MDP3",
        symbol: str = "MNQ.FUT",
        stype_in: str = "parent",
        timeframe_minutes: int = 5,
        bootstrap_bars: int = 60,
    ):
        self.api_key = api_key
        self.dataset = dataset
        self.symbol = symbol
        self.stype_in = stype_in
        self.timeframe_minutes = timeframe_minutes
        self.bootstrap_bars = bootstrap_bars
        self._db = self._import_databento()
        self._minute_history = self._bootstrap_minute_history()
        self._dataframe = resample_ohlcv(self._minute_history, self.timeframe_minutes)
        if self._dataframe.empty:
            raise LiveDataError("Databento bootstrap returned no bars.")

    @staticmethod
    def _import_databento():
        try:
            import databento as db
        except ImportError as exc:
            raise LiveDataError(
                "Databento provider requested but the 'databento' package is not installed."
            ) from exc
        return db

    def dataframe(self) -> pd.DataFrame:
        return self._dataframe.copy()

    def _bootstrap_minute_history(self) -> pd.DataFrame:
        end = datetime.now(timezone.utc)
        lookback_minutes = max(self.bootstrap_bars * self.timeframe_minutes * 2, 180)
        start = end - timedelta(minutes=lookback_minutes)

        client = self._db.Historical(self.api_key)
        store = client.timeseries.get_range(
            dataset=self.dataset,
            symbols=self.symbol,
            schema="ohlcv-1m",
            stype_in=self.stype_in,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        dataframe = normalize_databento_ohlcv(store.to_df())
        if dataframe.empty:
            raise LiveDataError("Databento historical bootstrap returned no 1-minute bars.")
        return dataframe

    def iter_bars(self):
        record_queue: queue.Queue[Any] = queue.Queue()
        live_client = self._db.Live(key=self.api_key)
        live_client.subscribe(
            dataset=self.dataset,
            schema="ohlcv-1m",
            symbols=self.symbol,
            stype_in=self.stype_in,
        )
        live_client.add_callback(record_queue.put)
        live_client.start()

        try:
            while True:
                record = record_queue.get()

                if hasattr(record, "is_heartbeat") and record.is_heartbeat():
                    continue
                if hasattr(record, "msg") and hasattr(record, "code"):
                    continue

                minute_bar = normalize_databento_ohlcv(record_to_frame(record))
                if minute_bar.empty:
                    continue

                self._minute_history = (
                    pd.concat([self._minute_history, minute_bar], ignore_index=True)
                    .drop_duplicates(subset=["datetime"], keep="last")
                    .sort_values("datetime")
                    .reset_index(drop=True)
                )
                five_minute = resample_ohlcv(self._minute_history, self.timeframe_minutes)
                if five_minute.empty:
                    continue

                latest = five_minute.iloc[-1]
                yield latest
        finally:
            try:
                live_client.stop()
            except Exception:
                pass


class TradovateProvider:
    """Tradovate chart subscription provider for 5-minute futures bars."""

    provider_name = "tradovate"
    emits_partial_bars = True

    def __init__(
        self,
        username: str,
        password: str,
        app_id: str,
        app_version: str = "1.0",
        cid: str = "0",
        sec: str = "",
        symbol: str = "MNQM2026",
        api_base_url: str = "https://demo.tradovateapi.com/v1",
        md_websocket_url: str = "wss://md.tradovateapi.com/v1/websocket",
        timeframe_minutes: int = 5,
        bootstrap_bars: int = 100,
    ):
        self.username = username
        self.password = password
        self.app_id = app_id
        self.app_version = app_version
        self.cid = cid
        self.sec = sec
        self.symbol = symbol
        self.api_base_url = api_base_url.rstrip("/")
        self.md_websocket_url = md_websocket_url
        self.timeframe_minutes = timeframe_minutes
        self.bootstrap_bars = bootstrap_bars
        self._requests = self._import_requests()
        self._websocket = self._import_websocket()

        if not all([self.username, self.password, self.app_id]):
            raise LiveDataError("Tradovate provider requires username, password, and app ID.")

        token_response = self._request_access_token()
        self.ws_token = token_response.get("mdAccessToken") or token_response.get("accessToken")
        if not self.ws_token:
            raise LiveDataError("Tradovate did not return a market-data access token.")

        self._dataframe = pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])

    @staticmethod
    def _import_requests():
        try:
            import requests
        except ImportError as exc:
            raise LiveDataError(
                "Tradovate provider requested but the 'requests' package is not installed."
            ) from exc
        return requests

    @staticmethod
    def _import_websocket():
        try:
            import websocket
        except ImportError as exc:
            raise LiveDataError(
                "Tradovate provider requested but the 'websocket-client' package is not installed."
            ) from exc
        return websocket

    def dataframe(self) -> pd.DataFrame:
        return self._dataframe.copy()

    def _request_access_token(self) -> dict[str, Any]:
        response = self._requests.post(
            f"{self.api_base_url}/auth/accesstokenrequest",
            json={
                "name": self.username,
                "password": self.password,
                "appId": self.app_id,
                "appVersion": self.app_version,
                "cid": self.cid,
                "sec": self.sec,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errorText"):
            raise LiveDataError(f"Tradovate auth failed: {payload['errorText']}")
        return payload

    def iter_bars(self):
        record_queue: queue.Queue[Any] = queue.Queue()
        auth_ready = threading.Event()
        subscription_ready = threading.Event()
        request_id = {"value": 1}

        def next_request_id() -> int:
            current = request_id["value"]
            request_id["value"] += 1
            return current

        def send_ws(ws_app, endpoint: str, body: dict[str, Any] | None = None, req_id: int | None = None):
            actual_id = 0 if req_id is None else req_id
            message = f"{endpoint}\n{actual_id}\n\n"
            if body is not None:
                message += json.dumps(body)
            ws_app.send(message)

        def on_open(ws_app):
            ws_app.send(f"authorize\n0\n\n{self.ws_token}")

        def on_message(ws_app, message: str):
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                return

            if isinstance(payload, list):
                for item in payload:
                    handle_payload(ws_app, item)
                return

            handle_payload(ws_app, payload)

        def handle_payload(ws_app, payload: dict[str, Any]):
            if payload.get("i") == 0:
                if payload.get("s") == 200:
                    auth_ready.set()
                    send_ws(
                        ws_app,
                        "md/getChart",
                        {
                            "symbol": self.symbol,
                            "chartDescription": {
                                "underlyingType": "MinuteBar",
                                "elementSize": self.timeframe_minutes,
                                "elementSizeUnit": "UnderlyingUnits",
                                "withHistogram": False,
                            },
                            "timeRange": {
                                "asMuchAsElements": self.bootstrap_bars,
                            },
                        },
                        req_id=next_request_id(),
                    )
                else:
                    record_queue.put(LiveDataError(f"Tradovate websocket authorization failed: {payload}"))
                return

            if payload.get("d", {}).get("historicalId") or payload.get("d", {}).get("realtimeId"):
                subscription_ready.set()
                return

            if payload.get("e") == "chart":
                for chart_packet in payload.get("d", {}).get("charts", []):
                    for bar in chart_packet.get("bars", []):
                        record_queue.put(bar)

        def on_error(ws_app, error):
            record_queue.put(LiveDataError(f"Tradovate websocket error: {error}"))

        ws_app = self._websocket.WebSocketApp(
            self.md_websocket_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
        )

        ws_thread = threading.Thread(
            target=lambda: ws_app.run_forever(ping_interval=20, ping_timeout=10),
            daemon=True,
            name="tradovate-md-websocket",
        )
        ws_thread.start()

        if not auth_ready.wait(timeout=15):
            ws_app.close()
            raise LiveDataError("Timed out waiting for Tradovate websocket authorization.")
        if not subscription_ready.wait(timeout=15):
            ws_app.close()
            raise LiveDataError("Timed out waiting for Tradovate chart subscription.")

        try:
            while True:
                item = record_queue.get()
                if isinstance(item, Exception):
                    raise item

                dataframe = normalize_tradovate_bars(pd.DataFrame([item]))
                if dataframe.empty:
                    continue

                latest = dataframe.iloc[-1]
                self._dataframe = (
                    pd.concat([self._dataframe, dataframe], ignore_index=True)
                    .drop_duplicates(subset=["datetime"], keep="last")
                    .sort_values("datetime")
                    .reset_index(drop=True)
                )
                yield latest
        finally:
            try:
                ws_app.close()
            except Exception:
                pass


class YahooFinanceProvider:
    """Yahoo Finance-backed provider using polled 5-minute futures bars."""

    provider_name = "yfinance"
    emits_partial_bars = True

    def __init__(
        self,
        symbol: str = "NQ=F",
        interval: str = "5m",
        period: str = "5d",
        poll_seconds: float = 15.0,
    ):
        self.symbol = symbol
        self.interval = interval
        self.period = period
        self.poll_seconds = max(5.0, float(poll_seconds))
        self._yf = self._import_yfinance()
        self._dataframe = self._fetch_history()
        if self._dataframe.empty:
            raise LiveDataError(f"Yahoo Finance returned no bars for {self.symbol}.")

    @staticmethod
    def _import_yfinance():
        try:
            import yfinance as yf
        except ImportError as exc:
            raise LiveDataError(
                "Yahoo Finance provider requested but the 'yfinance' package is not installed."
            ) from exc
        return yf

    def dataframe(self) -> pd.DataFrame:
        return self._dataframe.copy()

    def _fetch_history(self) -> pd.DataFrame:
        dataframe = self._yf.download(
            tickers=self.symbol,
            period=self.period,
            interval=self.interval,
            auto_adjust=False,
            progress=False,
            prepost=True,
            threads=False,
        )
        return normalize_yfinance_ohlcv(dataframe)

    def iter_bars(self):
        for _, row in self._dataframe.iterrows():
            yield row

        while True:
            time.sleep(self.poll_seconds)
            latest_frame = self._fetch_history()
            if latest_frame.empty:
                continue

            previous = self._dataframe.copy()
            self._dataframe = (
                pd.concat([self._dataframe, latest_frame], ignore_index=True)
                .drop_duplicates(subset=["datetime"], keep="last")
                .sort_values("datetime")
                .reset_index(drop=True)
            )

            previous_map = {
                row["datetime"]: (
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["volume"]),
                )
                for _, row in previous.iterrows()
            }

            for _, row in self._dataframe.iterrows():
                signature = (
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row["volume"]),
                )
                if previous_map.get(row["datetime"]) != signature:
                    yield row


class LiveDataHub:
    """Owns an in-memory bar window and updates it from a provider thread."""

    def __init__(
        self,
        provider,
        history_limit: int = 240,
        bootstrap_rows: int = 60,
        intrabar_updates: int = 5,
        replay_bar_seconds: float | None = None,
    ):
        self.provider = provider
        self.history_limit = history_limit
        self.bootstrap_rows = bootstrap_rows
        self.intrabar_updates = max(2, intrabar_updates)
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()
        self._version = 0

        dataframe = self.provider.dataframe()
        self.timeframe_minutes = infer_timeframe_minutes(dataframe) or 5
        configured_bar_seconds = replay_bar_seconds
        if configured_bar_seconds is None:
            env_value = os.getenv("LIVE_REPLAY_BAR_SECONDS")
            configured_bar_seconds = float(env_value) if env_value else float(self.timeframe_minutes * 60)
        self.replay_bar_seconds = max(1.0, float(configured_bar_seconds))
        self.phase_sleep_seconds = self.replay_bar_seconds / self.intrabar_updates

        initial_rows = dataframe.head(min(self.bootstrap_rows, len(dataframe))).copy()
        self._rows = initial_rows.reset_index(drop=True)
        self._stream_iter = self.provider.iter_bars()

        for _ in range(len(self._rows)):
            next(self._stream_iter)

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="live-data-hub")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                row = next(self._stream_iter)
            except StopIteration:
                return

            if getattr(self.provider, "emits_partial_bars", False):
                self._apply_partial_bar(row.to_dict())
                continue

            phases = self._build_bar_phases(row.to_dict())
            for phase in phases:
                if self._stop_event.is_set():
                    return

                self._apply_partial_bar(phase)
                time.sleep(self.phase_sleep_seconds)

    def dataframe(self) -> pd.DataFrame:
        with self._lock:
            return self._rows.copy()

    def version(self) -> int:
        with self._lock:
            return self._version

    def snapshot(self) -> dict[str, Any]:
        dataframe = self.dataframe()
        rows = []
        for _, row in dataframe.iterrows():
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

        latest_timestamp = rows[-1]["datetime"] if rows else None
        return {
            "provider": self.provider_name,
            "version": self.version(),
            "row_count": len(dataframe),
            "latest_timestamp": latest_timestamp,
            "timeframe_minutes": self.timeframe_minutes,
            "rows": rows,
        }

    def sse_payload(self) -> bytes:
        payload = json.dumps(self.snapshot())
        return f"event: bars\ndata: {payload}\n\n".encode("utf-8")

    def _apply_partial_bar(self, row: dict[str, Any]) -> None:
        row_frame = pd.DataFrame([row])
        with self._lock:
            if len(self._rows) and self._rows.iloc[-1]["datetime"] == row["datetime"]:
                self._rows = pd.concat([self._rows.iloc[:-1], row_frame], ignore_index=True)
            else:
                self._rows = pd.concat([self._rows, row_frame], ignore_index=True)

            self._rows = self._rows.tail(self.history_limit).reset_index(drop=True)
            self._version += 1

    def _build_bar_phases(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        open_price = float(row["open"])
        high_price = float(row["high"])
        low_price = float(row["low"])
        close_price = float(row["close"])
        volume = float(row["volume"])
        bullish = close_price >= open_price

        first_extreme = low_price if bullish else high_price
        second_extreme = high_price if bullish else low_price

        phases = [
            {
                "datetime": row["datetime"],
                "open": open_price,
                "high": open_price,
                "low": open_price,
                "close": open_price,
                "volume": max(volume * 0.12, 1.0),
            },
            {
                "datetime": row["datetime"],
                "open": open_price,
                "high": max(open_price, first_extreme),
                "low": min(open_price, first_extreme),
                "close": first_extreme,
                "volume": max(volume * 0.28, 1.0),
            },
            {
                "datetime": row["datetime"],
                "open": open_price,
                "high": max(open_price, high_price, first_extreme, second_extreme),
                "low": min(open_price, low_price, first_extreme, second_extreme),
                "close": second_extreme,
                "volume": max(volume * 0.56, 1.0),
            },
            {
                "datetime": row["datetime"],
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": (open_price + close_price) / 2,
                "volume": max(volume * 0.8, 1.0),
            },
            {
                "datetime": row["datetime"],
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            },
        ]
        return phases[: self.intrabar_updates]


def create_live_data_hub(
    data_path: str | Path,
    history_limit: int = 240,
    bootstrap_rows: int = 60,
    intrabar_updates: int = 5,
    replay_bar_seconds: float | None = None,
) -> LiveDataHub:
    provider_name = os.getenv("LIVE_DATA_PROVIDER", "").strip().lower()
    databento_key = os.getenv("DATABENTO_API_KEY", "").strip()

    if provider_name == "tradovate":
        provider = TradovateProvider(
            username=os.getenv("TRADOVATE_USERNAME", "").strip(),
            password=os.getenv("TRADOVATE_PASSWORD", "").strip(),
            app_id=os.getenv("TRADOVATE_APP_ID", "").strip(),
            app_version=os.getenv("TRADOVATE_APP_VERSION", "1.0").strip(),
            cid=os.getenv("TRADOVATE_CID", "0").strip(),
            sec=os.getenv("TRADOVATE_SEC", "").strip(),
            symbol=os.getenv("TRADOVATE_SYMBOL", "MNQM2026").strip(),
            api_base_url=os.getenv("TRADOVATE_API_BASE_URL", "https://demo.tradovateapi.com/v1").strip(),
            md_websocket_url=os.getenv("TRADOVATE_MD_WS_URL", "wss://md.tradovateapi.com/v1/websocket").strip(),
            timeframe_minutes=int(os.getenv("LIVE_TIMEFRAME_MINUTES", "5")),
            bootstrap_bars=bootstrap_rows,
        )
    elif provider_name in {"yfinance", "yahoo", "yahoo_finance"}:
        provider = YahooFinanceProvider(
            symbol=os.getenv("YFINANCE_SYMBOL", "NQ=F").strip(),
            interval=os.getenv("YFINANCE_INTERVAL", "5m").strip(),
            period=os.getenv("YFINANCE_PERIOD", "5d").strip(),
            poll_seconds=float(os.getenv("YFINANCE_POLL_SECONDS", "15")),
        )
    elif provider_name == "databento" or (not provider_name and databento_key):
        provider = DatabentoProvider(
            api_key=databento_key,
            dataset=os.getenv("DATABENTO_DATASET", "GLBX.MDP3"),
            symbol=os.getenv("DATABENTO_SYMBOL", "MNQ.FUT"),
            stype_in=os.getenv("DATABENTO_STYPE_IN", "parent"),
            timeframe_minutes=int(os.getenv("LIVE_TIMEFRAME_MINUTES", "5")),
            bootstrap_bars=bootstrap_rows,
        )
    else:
        provider = CsvReplayProvider(data_path)

    hub = LiveDataHub(
        provider=provider,
        history_limit=history_limit,
        bootstrap_rows=bootstrap_rows,
        intrabar_updates=intrabar_updates,
        replay_bar_seconds=replay_bar_seconds,
    )
    hub.start()
    return hub


def infer_timeframe_minutes(dataframe: pd.DataFrame) -> int | None:
    if len(dataframe) < 2 or "datetime" not in dataframe.columns:
        return None

    diffs = dataframe["datetime"].sort_values().diff().dropna()
    if diffs.empty:
        return None

    minutes = int(round(diffs.dt.total_seconds().median() / 60))
    return minutes if minutes > 0 else None


def normalize_databento_ohlcv(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])

    normalized = dataframe.reset_index().copy()
    if "ts_event" not in normalized.columns:
        raise LiveDataError("Databento OHLCV data missing ts_event.")

    normalized["datetime"] = pd.to_datetime(normalized["ts_event"], utc=True).dt.tz_convert(None)
    rename_map = {}
    if "open_" in normalized.columns:
        rename_map["open_"] = "open"
    if "high_" in normalized.columns:
        rename_map["high_"] = "high"
    if "low_" in normalized.columns:
        rename_map["low_"] = "low"
    if "close_" in normalized.columns:
        rename_map["close_"] = "close"
    normalized = normalized.rename(columns=rename_map)

    volume_column = "volume"
    if "volume" not in normalized.columns and "size" in normalized.columns:
        volume_column = "size"
    if "volume" not in normalized.columns and "volume" not in rename_map.values():
        normalized["volume"] = normalized[volume_column]

    required = ["datetime", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in normalized.columns]
    if missing:
        raise LiveDataError(f"Databento OHLCV data missing columns: {missing}")

    normalized = normalized[required].copy()
    normalized = normalized.dropna(subset=required).sort_values("datetime").reset_index(drop=True)
    return normalized


def resample_ohlcv(dataframe: pd.DataFrame, timeframe_minutes: int) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe

    resampled = (
        dataframe.set_index("datetime")
        .resample(f"{timeframe_minutes}min", label="left", closed="left")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )
    return resampled


def normalize_yfinance_ohlcv(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])

    normalized = dataframe.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        normalized.columns = normalized.columns.get_level_values(0)

    normalized = normalized.reset_index()
    datetime_column = None
    for candidate in ("Datetime", "Date", "index"):
        if candidate in normalized.columns:
            datetime_column = candidate
            break
    if datetime_column is None:
        raise LiveDataError("Yahoo Finance data missing a datetime column.")

    rename_map = {
        datetime_column: "datetime",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    normalized = normalized.rename(columns=rename_map)
    required = ["datetime", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in normalized.columns]
    if missing:
        raise LiveDataError(f"Yahoo Finance data missing columns: {missing}")

    market_timezone = os.getenv("MARKET_TIMEZONE", "America/New_York")
    normalized["datetime"] = pd.to_datetime(normalized["datetime"], utc=True, errors="coerce")
    normalized["datetime"] = normalized["datetime"].dt.tz_convert(market_timezone).dt.tz_localize(None)
    normalized = normalized[required].dropna(subset=["datetime", "open", "high", "low", "close"])
    normalized["volume"] = normalized["volume"].fillna(0)
    normalized = normalized.sort_values("datetime").reset_index(drop=True)
    return normalized


def record_to_frame(record: Any) -> pd.DataFrame:
    if hasattr(record, "to_dict"):
        payload = record.to_dict()
    elif isinstance(record, dict):
        payload = record
    else:
        payload = {}

    return pd.DataFrame([payload])


def normalize_tradovate_bars(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])

    normalized = dataframe.copy()
    normalized["datetime"] = pd.to_datetime(normalized["timestamp"], utc=True).dt.tz_convert(None)
    normalized["volume"] = (
        normalized.get("upVolume", 0).fillna(0)
        + normalized.get("downVolume", 0).fillna(0)
    )
    normalized = normalized[["datetime", "open", "high", "low", "close", "volume"]]
    normalized = normalized.dropna(subset=["datetime", "open", "high", "low", "close"]).sort_values("datetime").reset_index(drop=True)
    return normalized
