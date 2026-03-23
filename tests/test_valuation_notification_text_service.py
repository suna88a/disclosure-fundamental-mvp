from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory, DisclosurePriority
from app.services.investment_input_service import InvestmentMetricInputs
from app.services.valuation_metrics_service import build_valuation_metrics
from app.services.valuation_notification_service import build_valuation_notification_presentation
from app.services.valuation_notification_text_service import build_valuation_notification_text


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _disclosure(session: Session) -> Disclosure:
    company = Company(code="7203", name="Toyota Motor Corporation", name_ja="トヨタ自動車")
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
    session.commit()
    session.refresh(disclosure)
    return disclosure


def _inputs(
    *,
    reference_close: Decimal | None = Decimal("1000"),
    eps: Decimal | None = Decimal("100"),
    eps_source: str | None = "company_forecast_eps",
    eps_basis: str = "forecast",
    annual_dps: Decimal | None = Decimal("40"),
    annual_dps_source: str = "annual_dividend_after",
    warnings: tuple[str, ...] = (),
) -> InvestmentMetricInputs:
    return InvestmentMetricInputs(
        code="7203",
        disclosure_date=date(2026, 3, 19),
        reference_trade_date=date(2026, 3, 18) if reference_close is not None else None,
        reference_close=reference_close,
        reference_price_source="yfinance" if reference_close is not None else None,
        reference_price_symbol="7203.T" if reference_close is not None else None,
        eps=eps,
        eps_source=eps_source,
        eps_basis=eps_basis,
        annual_dps=annual_dps,
        annual_dps_source=annual_dps_source,
        warnings=warnings,
    )


def test_build_valuation_notification_text_shows_per() -> None:
    session = _build_session()
    disclosure = _disclosure(session)
    inputs = _inputs(eps_basis="forecast", annual_dps=None, annual_dps_source="missing")
    metrics = build_valuation_metrics(inputs)
    presentation = build_valuation_notification_presentation(inputs, metrics)

    text = build_valuation_notification_text(
        disclosure=disclosure,
        inputs=inputs,
        metrics=metrics,
        presentation=presentation,
    )

    assert text.headline == "7203 トヨタ自動車"
    assert any("PER(会社予想EPS): 10.0" in line for line in text.body_lines)
    assert text.shown_fields == ("per",)
    assert "dividend_yield" in text.omitted_fields


def test_build_valuation_notification_text_shows_dividend_yield() -> None:
    session = _build_session()
    disclosure = _disclosure(session)
    inputs = _inputs(eps=None, eps_source=None, eps_basis="unknown", annual_dps=Decimal("50"))
    metrics = build_valuation_metrics(inputs)
    presentation = build_valuation_notification_presentation(inputs, metrics)

    text = build_valuation_notification_text(
        disclosure=disclosure,
        inputs=inputs,
        metrics=metrics,
        presentation=presentation,
    )

    assert any("配当利回り: 5.0%" in line for line in text.body_lines)
    assert text.shown_fields == ("dividend_yield",)
    assert "per" in text.omitted_fields


def test_build_valuation_notification_text_shows_both() -> None:
    session = _build_session()
    disclosure = _disclosure(session)
    inputs = _inputs()
    metrics = build_valuation_metrics(inputs)
    presentation = build_valuation_notification_presentation(inputs, metrics)

    text = build_valuation_notification_text(
        disclosure=disclosure,
        inputs=inputs,
        metrics=metrics,
        presentation=presentation,
    )

    assert text.shown_fields == ("per", "dividend_yield")
    assert text.omitted_fields == ()


def test_build_valuation_notification_text_shows_neither_when_both_suppressed() -> None:
    session = _build_session()
    disclosure = _disclosure(session)
    inputs = _inputs(reference_close=None, eps=None, eps_source=None, eps_basis="unknown", annual_dps=None, annual_dps_source="missing")
    metrics = build_valuation_metrics(inputs)
    presentation = build_valuation_notification_presentation(inputs, metrics)

    text = build_valuation_notification_text(
        disclosure=disclosure,
        inputs=inputs,
        metrics=metrics,
        presentation=presentation,
    )

    assert text.shown_fields == ()
    assert text.omitted_fields == ("per", "dividend_yield")


def test_build_valuation_notification_text_hides_per_for_actual_eps_fallback() -> None:
    session = _build_session()
    disclosure = _disclosure(session)
    inputs = _inputs(eps=Decimal("50"), eps_source="eps", eps_basis="actual")
    metrics = build_valuation_metrics(inputs)
    presentation = build_valuation_notification_presentation(inputs, metrics)

    text = build_valuation_notification_text(
        disclosure=disclosure,
        inputs=inputs,
        metrics=metrics,
        presentation=presentation,
    )

    assert not any("PER(" in line for line in text.body_lines)
    assert "per" in text.omitted_fields


def test_build_valuation_notification_text_hides_dividend_yield_for_partial_dps() -> None:
    session = _build_session()
    disclosure = _disclosure(session)
    inputs = _inputs(annual_dps=Decimal("20"), annual_dps_source="partial", warnings=("annual_dps_partial",))
    metrics = build_valuation_metrics(inputs)
    presentation = build_valuation_notification_presentation(inputs, metrics)

    text = build_valuation_notification_text(
        disclosure=disclosure,
        inputs=inputs,
        metrics=metrics,
        presentation=presentation,
    )

    assert not any("配当利回り:" in line for line in text.body_lines)
    assert "dividend_yield" in text.omitted_fields
