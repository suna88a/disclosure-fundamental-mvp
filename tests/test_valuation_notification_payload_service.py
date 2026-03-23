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
from app.services.valuation_notification_payload_service import build_valuation_notification_draft_payload
from app.services.valuation_notification_service import build_valuation_notification_presentation
from app.services.valuation_notification_text_service import build_valuation_notification_text


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _disclosure(session: Session, category: DisclosureCategory = DisclosureCategory.GUIDANCE_REVISION) -> Disclosure:
    company = Company(code="7203", name="Toyota Motor Corporation", name_ja="トヨタ自動車")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-19T15:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=category,
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


def _build_payload(disclosure: Disclosure, inputs: InvestmentMetricInputs):
    metrics = build_valuation_metrics(inputs)
    presentation = build_valuation_notification_presentation(inputs, metrics)
    text = build_valuation_notification_text(
        disclosure=disclosure,
        inputs=inputs,
        metrics=metrics,
        presentation=presentation,
    )
    return build_valuation_notification_draft_payload(
        disclosure=disclosure,
        inputs=inputs,
        metrics=metrics,
        presentation=presentation,
        text=text,
    )


def test_build_valuation_notification_draft_payload_headline_format() -> None:
    session = _build_session()
    disclosure = _disclosure(session)

    payload = _build_payload(disclosure, _inputs())

    assert payload.title == "[業績予想の修正] 7203 トヨタ自動車"


def test_build_valuation_notification_draft_payload_with_valuation_lines() -> None:
    session = _build_session()
    disclosure = _disclosure(session)

    payload = _build_payload(disclosure, _inputs())

    assert "PER(会社予想EPS): 10.0" in payload.body
    assert "配当利回り: 4.0%" in payload.body
    assert payload.metadata["shown_fields"] == ["per", "dividend_yield"]
    assert payload.metadata["omitted_fields"] == []


def test_build_valuation_notification_draft_payload_without_valuation_lines() -> None:
    session = _build_session()
    disclosure = _disclosure(session)

    payload = _build_payload(
        disclosure,
        _inputs(reference_close=None, eps=None, eps_source=None, eps_basis="unknown", annual_dps=None, annual_dps_source="missing"),
    )

    assert "PER(" not in payload.body
    assert "配当利回り:" not in payload.body
    assert payload.metadata["shown_fields"] == []
    assert payload.metadata["omitted_fields"] == ["per", "dividend_yield"]


def test_build_valuation_notification_draft_payload_omits_per_for_actual_eps() -> None:
    session = _build_session()
    disclosure = _disclosure(session)

    payload = _build_payload(disclosure, _inputs(eps=Decimal("50"), eps_source="eps", eps_basis="actual", warnings=("eps_basis_actual",)))

    assert "PER(" not in payload.body
    assert "per_requires_forecast_eps" in payload.metadata["suppressed_reasons"]


def test_build_valuation_notification_draft_payload_omits_dividend_yield_for_partial_dps() -> None:
    session = _build_session()
    disclosure = _disclosure(session)

    payload = _build_payload(disclosure, _inputs(annual_dps=Decimal("20"), annual_dps_source="partial", warnings=("annual_dps_partial",)))

    assert "配当利回り:" not in payload.body
    assert "dividend_yield_requires_full_year_dps" in payload.metadata["suppressed_reasons"]


def test_build_valuation_notification_draft_payload_keeps_internal_metadata() -> None:
    session = _build_session()
    disclosure = _disclosure(session)

    payload = _build_payload(disclosure, _inputs(warnings=("eps_basis_actual",)))

    assert payload.metadata["disclosure_id"] == disclosure.id
    assert payload.metadata["company_code"] == "7203"
    assert payload.metadata["category"] == DisclosureCategory.GUIDANCE_REVISION.value
    assert payload.metadata["warnings"] == ["eps_basis_actual"]
