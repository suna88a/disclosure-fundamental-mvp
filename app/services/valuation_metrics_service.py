from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.investment_input_service import InvestmentMetricInputs


@dataclass(frozen=True)
class ValuationMetrics:
    forward_per: Decimal | None
    dividend_yield: Decimal | None
    eps_basis: str
    has_reference_close: bool
    has_eps: bool
    has_annual_dps: bool
    warnings: tuple[str, ...]


def calc_forward_per(inputs: InvestmentMetricInputs) -> Decimal | None:
    if inputs.reference_close is None or inputs.eps is None:
        return None
    if inputs.eps <= 0:
        return None
    return inputs.reference_close / inputs.eps


def calc_dividend_yield(inputs: InvestmentMetricInputs) -> Decimal | None:
    if inputs.reference_close is None or inputs.annual_dps is None:
        return None
    if inputs.reference_close <= 0:
        return None
    return inputs.annual_dps / inputs.reference_close


def build_valuation_metrics(inputs: InvestmentMetricInputs) -> ValuationMetrics:
    warnings = list(inputs.warnings)
    if inputs.eps is not None and inputs.eps <= 0:
        warnings.append("eps_non_positive")
    if inputs.reference_close is not None and inputs.reference_close <= 0:
        warnings.append("reference_close_non_positive")

    return ValuationMetrics(
        forward_per=calc_forward_per(inputs),
        dividend_yield=calc_dividend_yield(inputs),
        eps_basis=inputs.eps_basis,
        has_reference_close=inputs.reference_close is not None,
        has_eps=inputs.eps is not None,
        has_annual_dps=inputs.annual_dps is not None,
        warnings=tuple(warnings),
    )
