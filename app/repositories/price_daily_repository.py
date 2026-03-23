from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.price_daily import PriceDaily


@dataclass(frozen=True)
class PriceDailyCreateInput:
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


class PriceDailyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_code_and_trade_date(self, code: str, trade_date: date) -> PriceDaily | None:
        statement = select(PriceDaily).where(
            PriceDaily.code == code,
            PriceDaily.trade_date == trade_date,
        )
        return self.session.scalar(statement)

    def get_latest_before(self, code: str, target_date: date) -> PriceDaily | None:
        statement = (
            select(PriceDaily)
            .where(PriceDaily.code == code, PriceDaily.trade_date < target_date)
            .order_by(PriceDaily.trade_date.desc())
        )
        return self.session.scalar(statement)

    def get_latest_with_close_before(self, code: str, target_date: date) -> PriceDaily | None:
        statement = (
            select(PriceDaily)
            .where(
                PriceDaily.code == code,
                PriceDaily.trade_date < target_date,
                PriceDaily.close.is_not(None),
            )
            .order_by(PriceDaily.trade_date.desc())
        )
        return self.session.scalar(statement)

    def bulk_upsert(self, payloads: Sequence[PriceDailyCreateInput], *, force: bool = False) -> dict[str, int]:
        inserted = 0
        updated = 0
        skipped = 0

        for payload in payloads:
            row = self.get_by_code_and_trade_date(payload.code, payload.trade_date)
            if row is None:
                row = PriceDaily(
                    code=payload.code,
                    trade_date=payload.trade_date,
                    open=payload.open,
                    high=payload.high,
                    low=payload.low,
                    close=payload.close,
                    adj_close=payload.adj_close,
                    volume=payload.volume,
                    source=payload.source,
                    source_symbol=payload.source_symbol,
                    fetched_at=payload.fetched_at,
                )
                self.session.add(row)
                inserted += 1
                continue

            if not force and not self._has_changes(row, payload):
                skipped += 1
                continue

            row.open = payload.open
            row.high = payload.high
            row.low = payload.low
            row.close = payload.close
            row.adj_close = payload.adj_close
            row.volume = payload.volume
            row.source = payload.source
            row.source_symbol = payload.source_symbol
            row.fetched_at = payload.fetched_at
            updated += 1

        self.session.flush()
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    @staticmethod
    def _has_changes(row: PriceDaily, payload: PriceDailyCreateInput) -> bool:
        return any(
            getattr(row, field) != getattr(payload, field)
            for field in (
                "open",
                "high",
                "low",
                "close",
                "adj_close",
                "volume",
                "source",
                "source_symbol",
            )
        )
