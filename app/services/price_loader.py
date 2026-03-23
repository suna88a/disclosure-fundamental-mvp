from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.fetchers.price_fetcher import PriceFetcher, PriceFetchRecord
from app.repositories.price_daily_repository import PriceDailyCreateInput, PriceDailyRepository


@dataclass(frozen=True)
class PriceLoaderResult:
    processed: int
    fetched: int
    inserted: int
    updated: int
    skipped: int
    empty_codes: int
    failed: int
    dry_run: int


def load_prices(
    session: Session,
    *,
    fetcher: PriceFetcher,
    codes: Sequence[str],
    start_date: date,
    end_date: date,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, int]:
    payloads: list[PriceDailyCreateInput] = []
    empty_codes = 0
    failed = 0
    fetched = 0

    for code in codes:
        try:
            records = fetcher.fetch_range(str(code), start_date, end_date)
        except Exception:
            failed += 1
            continue

        if not records:
            empty_codes += 1
            continue

        fetched += len(records)
        payloads.extend(_to_payload(record) for record in records)

    if dry_run:
        return {
            "processed": len(codes),
            "fetched": fetched,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "empty_codes": empty_codes,
            "failed": failed,
            "dry_run": 1,
        }

    repository = PriceDailyRepository(session)
    upsert_result = repository.bulk_upsert(payloads, force=force)
    return {
        "processed": len(codes),
        "fetched": fetched,
        "inserted": upsert_result["inserted"],
        "updated": upsert_result["updated"],
        "skipped": upsert_result["skipped"],
        "empty_codes": empty_codes,
        "failed": failed,
        "dry_run": 0,
    }


def _to_payload(record: PriceFetchRecord) -> PriceDailyCreateInput:
    return PriceDailyCreateInput(
        code=record.code,
        trade_date=record.trade_date,
        open=record.open,
        high=record.high,
        low=record.low,
        close=record.close,
        adj_close=record.adj_close,
        volume=record.volume,
        source=record.source,
        source_symbol=record.source_symbol,
        fetched_at=record.fetched_at,
    )
