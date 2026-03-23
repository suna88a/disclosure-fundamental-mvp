from datetime import date
from decimal import Decimal

from app.services.investment_input_service import InvestmentMetricInputs
from app.services.valuation_metrics_service import (
    build_valuation_metrics,
    calc_dividend_yield,
    calc_forward_per,
)


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


def test_build_valuation_metrics_returns_normal_values() -> None:
    inputs = _inputs()

    metrics = build_valuation_metrics(inputs)

    assert calc_forward_per(inputs) == Decimal("10")
    assert calc_dividend_yield(inputs) == Decimal("0.04")
    assert metrics.forward_per == Decimal("10")
    assert metrics.dividend_yield == Decimal("0.04")
    assert metrics.eps_basis == "forecast"
    assert metrics.has_reference_close is True
    assert metrics.has_eps is True
    assert metrics.has_annual_dps is True
    assert metrics.warnings == ()


def test_build_valuation_metrics_returns_none_when_eps_missing() -> None:
    inputs = _inputs(eps=None, eps_source=None, eps_basis="unknown")

    metrics = build_valuation_metrics(inputs)

    assert metrics.forward_per is None
    assert metrics.dividend_yield == Decimal("0.04")
    assert metrics.has_eps is False
    assert metrics.eps_basis == "unknown"


def test_build_valuation_metrics_returns_none_when_eps_non_positive() -> None:
    inputs = _inputs(eps=Decimal("0"), eps_basis="actual", warnings=("eps_basis_actual",))

    metrics = build_valuation_metrics(inputs)

    assert metrics.forward_per is None
    assert "eps_non_positive" in metrics.warnings
    assert "eps_basis_actual" in metrics.warnings


def test_build_valuation_metrics_returns_none_when_annual_dps_missing() -> None:
    inputs = _inputs(annual_dps=None, annual_dps_source="missing")

    metrics = build_valuation_metrics(inputs)

    assert metrics.dividend_yield is None
    assert metrics.has_annual_dps is False


def test_build_valuation_metrics_returns_none_when_reference_close_missing() -> None:
    inputs = _inputs(reference_close=None, warnings=("reference_price_missing",))

    metrics = build_valuation_metrics(inputs)

    assert metrics.forward_per is None
    assert metrics.dividend_yield is None
    assert metrics.has_reference_close is False
    assert metrics.warnings == ("reference_price_missing",)


def test_build_valuation_metrics_preserves_input_warnings_and_sources() -> None:
    inputs = _inputs(
        eps=Decimal("50"),
        eps_source="eps",
        eps_basis="actual",
        annual_dps=Decimal("15"),
        annual_dps_source="partial",
        warnings=("annual_dps_partial", "eps_basis_actual"),
    )

    metrics = build_valuation_metrics(inputs)

    assert metrics.forward_per == Decimal("20")
    assert metrics.dividend_yield == Decimal("0.015")
    assert metrics.eps_basis == "actual"
    assert inputs.eps_source == "eps"
    assert inputs.annual_dps_source == "partial"
    assert metrics.warnings == ("annual_dps_partial", "eps_basis_actual")
