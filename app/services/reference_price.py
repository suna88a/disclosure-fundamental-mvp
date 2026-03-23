from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.price_daily_repository import PriceDailyRepository


@dataclass(frozen=True)
class ReferencePrice:
    code: str
    reference_trade_date: date
    close: Decimal
    source: str
    source_symbol: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_reference_price(session: Session, code: str, disclosure_date: date | datetime) -> ReferencePrice | None:
    target_date = disclosure_date.date() if isinstance(disclosure_date, datetime) else disclosure_date
    repository = PriceDailyRepository(session)
    row = repository.get_latest_with_close_before(str(code), target_date)
    if row is None:
        return None
    return ReferencePrice(
        code=row.code,
        reference_trade_date=row.trade_date,
        close=row.close,
        source=row.source,
        source_symbol=row.source_symbol,
    )
