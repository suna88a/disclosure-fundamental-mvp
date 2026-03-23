from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.company import Company
from app.models.price_daily import PriceDaily
from app.repositories.company_repository import CompanyRepository
from app.repositories.price_daily_repository import PriceDailyCreateInput, PriceDailyRepository
from app.services.reference_price import resolve_reference_price


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _payload(trade_date: date, close: str) -> PriceDailyCreateInput:
    return PriceDailyCreateInput(
        code="7203",
        trade_date=trade_date,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        adj_close=Decimal(close),
        volume=100,
        source="yfinance",
        source_symbol="7203.T",
        fetched_at=datetime.fromisoformat("2026-03-22T12:00:00+00:00"),
    )


def test_company_repository_list_active_codes_only_returns_active_codes() -> None:
    session = _build_session()
    session.add_all([
        Company(code="7203", name="Toyota", is_active=True),
        Company(code="6758", name="Sony", is_active=False),
        Company(code="9432", name="NTT", is_active=True),
    ])
    session.commit()

    codes = CompanyRepository(session).list_active_codes()

    assert codes == ["7203", "9432"]


def test_price_daily_repository_inserts_and_skips_duplicate_without_force() -> None:
    session = _build_session()
    repository = PriceDailyRepository(session)

    first = repository.bulk_upsert([_payload(date(2026, 3, 18), "1000")])
    second = repository.bulk_upsert([_payload(date(2026, 3, 18), "1000")])
    rows = session.query(PriceDaily).all()

    assert first == {"inserted": 1, "updated": 0, "skipped": 0}
    assert second == {"inserted": 0, "updated": 0, "skipped": 1}
    assert len(rows) == 1


def test_price_daily_repository_updates_duplicate_with_force() -> None:
    session = _build_session()
    repository = PriceDailyRepository(session)

    repository.bulk_upsert([_payload(date(2026, 3, 18), "1000")])
    result = repository.bulk_upsert([_payload(date(2026, 3, 18), "1010")], force=True)
    row = repository.get_by_code_and_trade_date("7203", date(2026, 3, 18))

    assert result == {"inserted": 0, "updated": 1, "skipped": 0}
    assert row is not None
    assert row.close == Decimal("1010")


def test_resolve_reference_price_returns_latest_prior_close() -> None:
    session = _build_session()
    repository = PriceDailyRepository(session)
    repository.bulk_upsert(
        [
            _payload(date(2026, 3, 17), "995"),
            _payload(date(2026, 3, 18), "1000"),
            _payload(date(2026, 3, 21), "1020"),
        ]
    )

    result = resolve_reference_price(session, "7203", date(2026, 3, 22))

    assert result is not None
    assert result.code == "7203"
    assert result.reference_trade_date == date(2026, 3, 21)
    assert result.close == Decimal("1020")
    assert result.source == "yfinance"
    assert result.source_symbol == "7203.T"


def test_resolve_reference_price_falls_back_to_previous_trade_date() -> None:
    session = _build_session()
    repository = PriceDailyRepository(session)
    repository.bulk_upsert(
        [
            _payload(date(2026, 3, 18), "1000"),
            _payload(date(2026, 3, 21), "1020"),
        ]
    )

    result = resolve_reference_price(session, "7203", date(2026, 3, 21))

    assert result is not None
    assert result.reference_trade_date == date(2026, 3, 18)
    assert result.close == Decimal("1000")


def test_resolve_reference_price_returns_none_when_no_prior_data() -> None:
    session = _build_session()

    result = resolve_reference_price(session, "7203", date(2026, 3, 21))

    assert result is None
