from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import importlib
import math
import re
from typing import Any, Protocol


JAPAN_EQUITY_CODE_PATTERN = re.compile(r"^\d{4,6}$")


@dataclass(frozen=True)
class PriceFetchRecord:
    code: str
    trade_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    adj_close: Decimal | None
    volume: int | None
    source: str
    source_symbol: str
    fetched_at: datetime


class PriceFetcher(Protocol):
    def fetch_daily(self, code: str, trade_date: date) -> PriceFetchRecord | None:
        ...

    def fetch_range(self, code: str, start_date: date, end_date: date) -> list[PriceFetchRecord]:
        ...


class YFinancePriceFetcher:
    source_name = "yfinance"

    def build_symbol(self, code: str) -> str:
        normalized = str(code).strip()
        if not JAPAN_EQUITY_CODE_PATTERN.fullmatch(normalized):
            raise ValueError(f"Unsupported Japan equity code format: {code}")
        return f"{normalized}.T"

    def fetch_daily(self, code: str, trade_date: date) -> PriceFetchRecord | None:
        rows = self.fetch_range(code, trade_date, trade_date)
        return rows[0] if rows else None

    def fetch_range(self, code: str, start_date: date, end_date: date) -> list[PriceFetchRecord]:
        if start_date > end_date:
            raise ValueError("start_date must be earlier than or equal to end_date")

        symbol = self.build_symbol(code)
        rows = self._fetch_history_rows(symbol, start_date, end_date)
        fetched_at = datetime.now(UTC)
        records: list[PriceFetchRecord] = []

        for row in rows:
            trade_date = self._extract_trade_date(row.get("trade_date"))
            if trade_date is None or trade_date < start_date or trade_date > end_date:
                continue
            records.append(
                PriceFetchRecord(
                    code=str(code),
                    trade_date=trade_date,
                    open=self._to_decimal(row.get("open")),
                    high=self._to_decimal(row.get("high")),
                    low=self._to_decimal(row.get("low")),
                    close=self._to_decimal(row.get("close")),
                    adj_close=self._to_decimal(row.get("adj_close")),
                    volume=self._to_int(row.get("volume")),
                    source=self.source_name,
                    source_symbol=symbol,
                    fetched_at=fetched_at,
                )
            )

        records.sort(key=lambda item: item.trade_date)
        return records

    def _fetch_history_rows(self, symbol: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
        yfinance = importlib.import_module("yfinance")
        ticker = yfinance.Ticker(symbol)
        history = ticker.history(
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            actions=False,
        )
        if history is None or getattr(history, "empty", False):
            return []

        rows: list[dict[str, Any]] = []
        for index, row in history.iterrows():
            rows.append(
                {
                    "trade_date": index,
                    "open": self._value_from_row(row, "Open"),
                    "high": self._value_from_row(row, "High"),
                    "low": self._value_from_row(row, "Low"),
                    "close": self._value_from_row(row, "Close"),
                    "adj_close": self._value_from_row(row, "Adj Close") or self._value_from_row(row, "Close"),
                    "volume": self._value_from_row(row, "Volume"),
                }
            )
        return rows

    @staticmethod
    def _value_from_row(row: Any, key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        getter = getattr(row, "get", None)
        if callable(getter):
            return getter(key)
        try:
            return row[key]
        except Exception:
            return None

    @staticmethod
    def _extract_trade_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        date_attr = getattr(value, "date", None)
        if callable(date_attr):
            result = date_attr()
            if isinstance(result, date):
                return result
        return None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        if isinstance(value, float) and math.isnan(value):
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        return Decimal(text)

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        return int(float(text))
