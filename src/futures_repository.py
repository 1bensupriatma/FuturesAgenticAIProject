import json
from pathlib import Path

import pandas as pd


class FuturesDataError(Exception):
    """Raised when futures data cannot be loaded or queried safely."""


class FuturesDataRepository:
    """Loads a futures CSV and normalizes common column-name variants."""

    COLUMN_ALIASES = {
        "date": ["date", "datetime", "timestamp", "trading_date", "trade_date"],
        "symbol": ["symbol", "root_symbol", "root", "asset", "underlying", "market"],
        "contract": ["contract", "contract_symbol", "instrument", "ticker", "code"],
        "expiry": ["expiry", "expiration", "expiration_date", "expiry_date", "maturity"],
        "open": ["open", "open_price", "px_open"],
        "high": ["high", "high_price", "px_high"],
        "low": ["low", "low_price", "px_low"],
        "close": ["close", "settle", "settlement", "last", "close_price", "px_close"],
        "volume": ["volume", "vol", "trade_volume"],
        "open_interest": ["open_interest", "oi"],
    }

    def __init__(self, csv_path):
        self.csv_path = Path(csv_path)
        self.dataframe = self._load_csv(self.csv_path)
        self.columns = self._resolve_columns(self.dataframe.columns)
        self.dataframe = self._normalize_dataframe(self.dataframe, self.columns)

    @classmethod
    def from_default_path(cls, csv_path=None):
        path = csv_path or Path("data/sample_futures_data.csv")
        return cls(path)

    def _load_csv(self, csv_path):
        if not csv_path.exists():
            raise FuturesDataError(
                f"Futures data file not found: {csv_path}. "
                "Set a valid CSV path when creating the repository."
            )

        try:
            dataframe = pd.read_csv(csv_path)
        except Exception as exc:
            raise FuturesDataError(f"Could not read futures CSV: {exc}") from exc

        if dataframe.empty:
            raise FuturesDataError(f"Futures CSV is empty: {csv_path}")

        return dataframe

    def _resolve_columns(self, columns):
        lowered = {str(column).strip().lower(): column for column in columns}
        resolved = {}

        for target, aliases in self.COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in lowered:
                    resolved[target] = lowered[alias]
                    break

        if "date" not in resolved:
            raise FuturesDataError("CSV must include a date-like column.")
        if "symbol" not in resolved and "contract" not in resolved:
            raise FuturesDataError("CSV must include either a symbol-like or contract-like column.")

        return resolved

    def _normalize_dataframe(self, dataframe, columns):
        normalized = dataframe.copy()
        rename_map = {source: target for target, source in columns.items()}
        normalized = normalized.rename(columns=rename_map)

        if "symbol" not in normalized.columns and "contract" in normalized.columns:
            normalized["symbol"] = normalized["contract"]

        if "contract" not in normalized.columns:
            normalized["contract"] = normalized["symbol"]

        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        normalized = normalized.dropna(subset=["date", "symbol", "contract"]).copy()
        normalized["symbol"] = normalized["symbol"].astype(str).str.strip()
        normalized["contract"] = normalized["contract"].astype(str).str.strip()

        if "expiry" in normalized.columns:
            normalized["expiry"] = pd.to_datetime(normalized["expiry"], errors="coerce")

        for numeric_col in ("open", "high", "low", "close", "volume", "open_interest"):
            if numeric_col in normalized.columns:
                normalized[numeric_col] = pd.to_numeric(normalized[numeric_col], errors="coerce")

        normalized = normalized.sort_values(["symbol", "contract", "date"]).reset_index(drop=True)
        return normalized

    @staticmethod
    def _iso_or_none(value):
        if pd.isna(value):
            return None
        if hasattr(value, "isoformat"):
            return value.date().isoformat() if hasattr(value, "date") else value.isoformat()
        return str(value)

    def _filter(self, symbol=None, contract=None, start_date=None, end_date=None):
        df = self.dataframe

        if symbol:
            df = df[df["symbol"].str.lower() == str(symbol).strip().lower()]
        if contract:
            df = df[df["contract"].str.lower() == str(contract).strip().lower()]
        if start_date:
            start_ts = pd.to_datetime(start_date, errors="coerce")
            df = df[df["date"] >= start_ts]
        if end_date:
            end_ts = pd.to_datetime(end_date, errors="coerce")
            df = df[df["date"] <= end_ts]

        return df.copy()

    def available_symbols(self):
        return sorted(value for value in self.dataframe["symbol"].dropna().unique().tolist() if value)

    def list_contracts(self, symbol=None):
        df = self._filter(symbol=symbol)
        if df.empty:
            return []

        columns = ["symbol", "contract"]
        if "expiry" in df.columns:
            columns.append("expiry")

        records = df[columns].drop_duplicates().sort_values(columns[:2]).to_dict("records")
        for record in records:
            if "expiry" in record:
                record["expiry"] = self._iso_or_none(record["expiry"])
        return records

    def get_contract_snapshot(self, symbol=None, date=None, contract=None):
        df = self._filter(symbol=symbol, contract=contract)
        if df.empty:
            return {"error": "No matching rows found for the requested symbol/contract."}

        if date:
            target_date = pd.to_datetime(date, errors="coerce")
            same_day = df[df["date"] == target_date]
            row = same_day.iloc[-1] if not same_day.empty else None
        else:
            row = None

        if row is None:
            row = df.iloc[-1]

        snapshot = {
            "symbol": row["symbol"],
            "contract": row["contract"],
            "date": self._iso_or_none(row["date"]),
        }
        if "expiry" in df.columns:
            snapshot["expiry"] = self._iso_or_none(row.get("expiry"))
        for numeric_col in ("open", "high", "low", "close", "volume", "open_interest"):
            if numeric_col in df.columns and not pd.isna(row.get(numeric_col)):
                snapshot[numeric_col] = float(row[numeric_col])
        return snapshot

    def summarize_price_move(self, symbol, start_date, end_date, contract=None):
        df = self._filter(symbol=symbol, contract=contract, start_date=start_date, end_date=end_date)
        if df.empty:
            return {"error": "No rows found in the requested date range."}
        if "close" not in df.columns:
            return {"error": "Close/settlement column is required for price-move summaries."}

        grouped = df.sort_values("date").groupby("contract", as_index=False)
        summaries = []
        for _, group in grouped:
            first_row = group.iloc[0]
            last_row = group.iloc[-1]
            start_close = first_row.get("close")
            end_close = last_row.get("close")
            if pd.isna(start_close) or pd.isna(end_close):
                continue

            absolute_change = float(end_close - start_close)
            percent_change = None if start_close == 0 else float((absolute_change / start_close) * 100)
            summaries.append(
                {
                    "symbol": last_row["symbol"],
                    "contract": last_row["contract"],
                    "start_date": self._iso_or_none(first_row["date"]),
                    "end_date": self._iso_or_none(last_row["date"]),
                    "start_close": float(start_close),
                    "end_close": float(end_close),
                    "absolute_change": absolute_change,
                    "percent_change": percent_change,
                }
            )

        if not summaries:
            return {"error": "No valid close-price pairs were found in the requested range."}
        return summaries

    def calculate_term_structure(self, symbol, date=None):
        df = self._filter(symbol=symbol)
        if df.empty:
            return {"error": "No rows found for the requested symbol."}
        if "close" not in df.columns:
            return {"error": "Close/settlement column is required for term-structure analysis."}
        if "expiry" not in df.columns:
            return {"error": "Expiry column is required for term-structure analysis."}

        if date:
            target_date = pd.to_datetime(date, errors="coerce")
            df = df[df["date"] == target_date]
        else:
            latest_date = df["date"].max()
            df = df[df["date"] == latest_date]

        df = df.dropna(subset=["expiry", "close"]).sort_values(["expiry", "contract"])
        if df.empty:
            return {"error": "No valid expiry/close rows found for the requested date."}

        term_points = []
        for _, row in df.iterrows():
            term_points.append(
                {
                    "symbol": row["symbol"],
                    "contract": row["contract"],
                    "date": self._iso_or_none(row["date"]),
                    "expiry": self._iso_or_none(row["expiry"]),
                    "close": float(row["close"]),
                }
            )

        first_close = term_points[0]["close"]
        last_close = term_points[-1]["close"]
        shape = "flat"
        if last_close > first_close:
            shape = "contango"
        elif last_close < first_close:
            shape = "backwardation"

        return {"curve_date": term_points[0]["date"], "shape": shape, "contracts": term_points}

    def detect_rollover(self, symbol, start_date=None, end_date=None):
        df = self._filter(symbol=symbol, start_date=start_date, end_date=end_date)
        if df.empty:
            return {"error": "No rows found for the requested rollover window."}
        if "volume" not in df.columns and "open_interest" not in df.columns:
            return {"error": "Volume or open_interest column is required for rollover detection."}

        metric = "open_interest" if "open_interest" in df.columns else "volume"
        ranked = (
            df.dropna(subset=[metric])
            .sort_values(["date", metric, "contract"], ascending=[True, False, True])
            .groupby("date", as_index=False)
            .first()
        )
        if ranked.empty:
            return {"error": f"No valid {metric} rows found for rollover detection."}

        events = []
        previous_contract = None
        for _, row in ranked.sort_values("date").iterrows():
            current_contract = row["contract"]
            if previous_contract and current_contract != previous_contract:
                events.append(
                    {
                        "date": self._iso_or_none(row["date"]),
                        "from_contract": previous_contract,
                        "to_contract": current_contract,
                        "signal_metric": metric,
                        "signal_value": float(row[metric]),
                    }
                )
            previous_contract = current_contract

        return {
            "symbol": symbol,
            "signal_metric": metric,
            "dominant_contracts": [
                {
                    "date": self._iso_or_none(row["date"]),
                    "contract": row["contract"],
                    metric: float(row[metric]),
                }
                for _, row in ranked.sort_values("date").iterrows()
            ],
            "rollover_events": events,
        }

    def to_json(self, payload):
        return json.dumps(payload, default=str)
