from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.dividend_revision import DividendRevision
from app.models.enums import DisclosureCategory, DisclosurePriority, RevisionDirection
from app.models.financial_report import FinancialReport
from app.models.price_daily import PriceDaily
from app.services.investment_input_service import get_disclosure_investment_metric_inputs


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _create_disclosure(session: Session, code: str = "7203") -> Disclosure:
    company = Company(code=code, name="Toyota Motor Corporation", name_ja="トヨタ自動車")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-19T15:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=DisclosureCategory.GUIDANCE_REVISION,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/disclosure",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    return disclosure


def test_get_disclosure_investment_metric_inputs_returns_forecast_eps_basis() -> None:
    session = _build_session()
    disclosure = _create_disclosure(session)
    session.add(
        FinancialReport(
            disclosure_id=disclosure.id,
            eps=Decimal("80.5"),
            company_forecast_eps=Decimal("120.0"),
            extraction_version="v1",
        )
    )
    session.add(
        DividendRevision(
            disclosure_id=disclosure.id,
            annual_dividend_after=Decimal("95"),
            revision_direction=RevisionDirection.UP,
        )
    )
    session.add(
        PriceDaily(
            code="7203",
            trade_date=date(2026, 3, 18),
            open=Decimal("1000"),
            high=Decimal("1010"),
            low=Decimal("995"),
            close=Decimal("1005"),
            adj_close=Decimal("1005"),
            volume=100,
            source="yfinance",
            source_symbol="7203.T",
        )
    )
    session.commit()

    result = get_disclosure_investment_metric_inputs(session, disclosure)

    assert result.eps == Decimal("120.0")
    assert result.eps_source == "company_forecast_eps"
    assert result.eps_basis == "forecast"
    assert result.annual_dps == Decimal("95")
    assert result.annual_dps_source == "annual_dividend_after"
    assert result.warnings == ()


def test_get_disclosure_investment_metric_inputs_falls_back_to_actual_eps() -> None:
    session = _build_session()
    disclosure = _create_disclosure(session)
    session.add(
        FinancialReport(
            disclosure_id=disclosure.id,
            eps=Decimal("80.5"),
            extraction_version="v1",
        )
    )
    session.add(
        PriceDaily(
            code="7203",
            trade_date=date(2026, 3, 18),
            open=Decimal("1000"),
            high=Decimal("1010"),
            low=Decimal("995"),
            close=Decimal("1005"),
            adj_close=Decimal("1005"),
            volume=100,
            source="yfinance",
            source_symbol="7203.T",
        )
    )
    session.commit()

    result = get_disclosure_investment_metric_inputs(session, disclosure)

    assert result.eps == Decimal("80.5")
    assert result.eps_source == "eps"
    assert result.eps_basis == "actual"
    assert "eps_basis_actual" in result.warnings
    assert "annual_dps_missing" in result.warnings


def test_get_disclosure_investment_metric_inputs_returns_unknown_when_eps_missing() -> None:
    session = _build_session()
    disclosure = _create_disclosure(session)
    session.commit()

    result = get_disclosure_investment_metric_inputs(session, disclosure)

    assert result.eps is None
    assert result.eps_source is None
    assert result.eps_basis == "unknown"
    assert result.annual_dps is None
    assert result.annual_dps_source == "missing"
    assert result.warnings == ("reference_price_missing", "eps_missing", "annual_dps_missing")


def test_get_disclosure_investment_metric_inputs_uses_previous_business_day_price() -> None:
    session = _build_session()
    disclosure = _create_disclosure(session)
    session.add_all(
        [
            PriceDaily(
                code="7203",
                trade_date=date(2026, 3, 16),
                open=Decimal("990"),
                high=Decimal("1000"),
                low=Decimal("985"),
                close=Decimal("995"),
                adj_close=Decimal("995"),
                volume=100,
                source="yfinance",
                source_symbol="7203.T",
            ),
            PriceDaily(
                code="7203",
                trade_date=date(2026, 3, 18),
                open=Decimal("1000"),
                high=Decimal("1010"),
                low=Decimal("995"),
                close=Decimal("1005"),
                adj_close=Decimal("1005"),
                volume=100,
                source="yfinance",
                source_symbol="7203.T",
            ),
            PriceDaily(
                code="7203",
                trade_date=date(2026, 3, 19),
                open=Decimal("1010"),
                high=Decimal("1020"),
                low=Decimal("1008"),
                close=Decimal("1015"),
                adj_close=Decimal("1015"),
                volume=100,
                source="yfinance",
                source_symbol="7203.T",
            ),
        ]
    )
    session.commit()

    result = get_disclosure_investment_metric_inputs(session, disclosure)

    assert result.reference_trade_date == date(2026, 3, 18)
    assert result.reference_close == Decimal("1005")


def test_get_disclosure_investment_metric_inputs_marks_partial_annual_dps() -> None:
    session = _build_session()
    disclosure = _create_disclosure(session)
    session.add(
        DividendRevision(
            disclosure_id=disclosure.id,
            year_end_dividend_after=Decimal("40"),
            revision_direction=RevisionDirection.UP,
        )
    )
    session.commit()

    result = get_disclosure_investment_metric_inputs(session, disclosure)

    assert result.annual_dps == Decimal("40")
    assert result.annual_dps_source == "partial"
    assert "annual_dps_partial" in result.warnings
