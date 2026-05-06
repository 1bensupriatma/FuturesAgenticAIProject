"""Yahoo Finance live-data support for the local FibAgent web app."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import pandas as pd


class LiveDataError(Exception):
    """Raised when Yahoo Finance data cannot be loaded safely."""


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
                "The 'yfinance' package is required for live FibAgent data."
            ) from exc
        return yf

    def dataframe(self) -> pd.DataFrame:
        """Return the current Yahoo Finance bar history."""
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
        """Yield existing bars, then poll Yahoo Finance for changed bars."""
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
                row["datetime"]: _bar_signature(row)
                for _, row in previous.iterrows()
            }

            for _, row in self._dataframe.iterrows():
                if previous_map.get(row["datetime"]) != _bar_signature(row):
                    yield row


class LiveDataHub:
    """Owns an in-memory Yahoo Finance bar window and updates it in a thread."""

    def __init__(
        self,
        provider: YahooFinanceProvider,
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
        self._thread: threading.Thread | None = None
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

            for phase in self._build_bar_phases(row.to_dict()):
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
        """Build simulated intrabar phases for non-partial providers.

        Yahoo Finance emits complete polled bars today, but this helper keeps the
        hub stable if the provider flag changes later.
        """
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
    data_path: str | Path | None = None,
    history_limit: int = 240,
    bootstrap_rows: int = 60,
    intrabar_updates: int = 5,
    replay_bar_seconds: float | None = None,
) -> LiveDataHub:
    """Create the Yahoo Finance live-data hub used by the website."""
    provider = YahooFinanceProvider(
        symbol=os.getenv("YFINANCE_SYMBOL", "NQ=F").strip(),
        interval=os.getenv("YFINANCE_INTERVAL", "5m").strip(),
        period=os.getenv("YFINANCE_PERIOD", "5d").strip(),
        poll_seconds=float(os.getenv("YFINANCE_POLL_SECONDS", "15")),
    )
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


def normalize_yfinance_ohlcv(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize yfinance OHLCV output into FibAgent's bar schema."""
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

    normalized = normalized.rename(
        columns={
            datetime_column: "datetime",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
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


def _bar_signature(row) -> tuple[float, float, float, float, float]:
    return (
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        float(row["volume"]),
    )
