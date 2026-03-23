from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.repositories.price_daily_repository import PriceDailyCreateInput, PriceDailyRepository
from app.services.reference_price import ReferencePrice, resolve_reference_price


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _payload(trade_date: date, close: str | None) -> PriceDailyCreateInput:
    return PriceDailyCreateInput(
        code="7203",
        trade_date=trade_date,
        open=Decimal("1000") if close is not None else None,
        high=Decimal("1005") if close is not None else None,
        low=Decimal("995") if close is not None else None,
        close=Decimal(close) if close is not None else None,
        adj_close=Decimal(close) if close is not None else None,
        volume=100,
        source="yfinance",
        source_symbol="7203.T",
        fetched_at=datetime.fromisoformat("2026-03-22T12:00:00+00:00"),
    )


def test_resolve_reference_price_returns_fixed_contract() -> None:
    session = _build_session()
    PriceDailyRepository(session).bulk_upsert([_payload(date(2026, 3, 18), "1000")])

    result = resolve_reference_price(session, "7203", datetime.fromisoformat("2026-03-19T15:00:00"))

    assert isinstance(result, ReferencePrice)
    assert result == ReferencePrice(
        code="7203",
        reference_trade_date=date(2026, 3, 18),
        close=Decimal("1000"),
        source="yfinance",
        source_symbol="7203.T",
    )
    assert result.to_dict() == {
        "code": "7203",
        "reference_trade_date": date(2026, 3, 18),
        "close": Decimal("1000"),
        "source": "yfinance",
        "source_symbol": "7203.T",
    }


def test_resolve_reference_price_returns_latest_prior_close() -> None:
    session = _build_session()
    PriceDailyRepository(session).bulk_upsert(
        [
            _payload(date(2026, 3, 17), "995"),
            _payload(date(2026, 3, 18), "1000"),
            _payload(date(2026, 3, 21), "1020"),
        ]
    )

    result = resolve_reference_price(session, "7203", datetime.fromisoformat("2026-03-22T15:00:00"))

    assert result is not None
    assert result.code == "7203"
    assert result.reference_trade_date == date(2026, 3, 21)
    assert result.close == Decimal("1020")
    assert result.source == "yfinance"
    assert result.source_symbol == "7203.T"


def test_resolve_reference_price_ignores_same_day_price() -> None:
    session = _build_session()
    PriceDailyRepository(session).bulk_upsert(
        [
            _payload(date(2026, 3, 18), "1000"),
            _payload(date(2026, 3, 19), "1010"),
        ]
    )

    result = resolve_reference_price(session, "7203", date(2026, 3, 19))

    assert result is not None
    assert result.reference_trade_date == date(2026, 3, 18)
    assert result.close == Decimal("1000")


def test_resolve_reference_price_falls_back_past_missing_close() -> None:
    session = _build_session()
    PriceDailyRepository(session).bulk_upsert(
        [
            _payload(date(2026, 3, 17), "995"),
            _payload(date(2026, 3, 18), None),
            _payload(date(2026, 3, 19), None),
        ]
    )

    result = resolve_reference_price(session, "7203", date(2026, 3, 20))

    assert result is not None
    assert result.reference_trade_date == date(2026, 3, 17)
    assert result.close == Decimal("995")


def test_resolve_reference_price_returns_none_when_no_prior_data() -> None:
    session = _build_session()

    result = resolve_reference_price(session, "7203", date(2026, 3, 21))

    assert result is None
