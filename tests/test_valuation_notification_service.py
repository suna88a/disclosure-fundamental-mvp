from datetime import date
from decimal import Decimal

from app.services.investment_input_service import InvestmentMetricInputs
from app.services.valuation_metrics_service import build_valuation_metrics
from app.services.valuation_notification_service import build_valuation_notification_presentation


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


def test_build_valuation_notification_presentation_shows_per_for_forecast_eps() -> None:
    inputs = _inputs(eps_basis="forecast")
    metrics = build_valuation_metrics(inputs)

    presentation = build_valuation_notification_presentation(inputs, metrics)

    assert presentation.show_per is True
    assert presentation.per_label == "PER(会社予想EPS)"
    assert presentation.show_dividend_yield is True
    assert presentation.dividend_yield_label == "配当利回り"
    assert presentation.suppressed_reasons == ()


def test_build_valuation_notification_presentation_suppresses_per_for_actual_eps() -> None:
    inputs = _inputs(eps=Decimal("50"), eps_source="eps", eps_basis="actual", warnings=("eps_basis_actual",))
    metrics = build_valuation_metrics(inputs)

    presentation = build_valuation_notification_presentation(inputs, metrics)

    assert presentation.show_per is False
    assert presentation.per_label is None
    assert "per_requires_forecast_eps" in presentation.suppressed_reasons
    assert presentation.warnings == ("eps_basis_actual",)


def test_build_valuation_notification_presentation_suppresses_dividend_yield_for_partial_dps() -> None:
    inputs = _inputs(annual_dps=Decimal("20"), annual_dps_source="partial", warnings=("annual_dps_partial",))
    metrics = build_valuation_metrics(inputs)

    presentation = build_valuation_notification_presentation(inputs, metrics)

    assert presentation.show_dividend_yield is False
    assert presentation.dividend_yield_label is None
    assert "dividend_yield_requires_full_year_dps" in presentation.suppressed_reasons
    assert presentation.warnings == ("annual_dps_partial",)


def test_build_valuation_notification_presentation_suppresses_when_reference_close_missing() -> None:
    inputs = _inputs(reference_close=None, warnings=("reference_price_missing",))
    metrics = build_valuation_metrics(inputs)

    presentation = build_valuation_notification_presentation(inputs, metrics)

    assert presentation.show_per is False
    assert presentation.show_dividend_yield is False
    assert "per_unavailable" in presentation.suppressed_reasons
    assert "dividend_yield_unavailable" in presentation.suppressed_reasons
    assert presentation.warnings == ("reference_price_missing",)


def test_build_valuation_notification_presentation_preserves_warnings_and_reasons() -> None:
    inputs = _inputs(
        eps=Decimal("0"),
        eps_basis="actual",
        annual_dps=Decimal("15"),
        annual_dps_source="partial",
        warnings=("eps_basis_actual", "annual_dps_partial"),
    )
    metrics = build_valuation_metrics(inputs)

    presentation = build_valuation_notification_presentation(inputs, metrics)

    assert presentation.show_per is False
    assert presentation.show_dividend_yield is False
    assert "per_unavailable" in presentation.suppressed_reasons
    assert "dividend_yield_requires_full_year_dps" in presentation.suppressed_reasons
    assert "eps_non_positive" in presentation.warnings
    assert "annual_dps_partial" in presentation.warnings
