from __future__ import annotations

from dataclasses import dataclass

from app.services.investment_input_service import InvestmentMetricInputs
from app.services.valuation_metrics_service import ValuationMetrics


@dataclass(frozen=True)
class ValuationNotificationPresentation:
    show_per: bool
    show_dividend_yield: bool
    per_label: str | None
    dividend_yield_label: str | None
    suppressed_reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def build_valuation_notification_presentation(
    inputs: InvestmentMetricInputs,
    metrics: ValuationMetrics,
) -> ValuationNotificationPresentation:
    suppressed_reasons: list[str] = []

    show_per = metrics.forward_per is not None
    per_label: str | None = None
    if not show_per:
        suppressed_reasons.append("per_unavailable")
    elif metrics.eps_basis != "forecast":
        show_per = False
        suppressed_reasons.append("per_requires_forecast_eps")
    else:
        per_label = "PER(会社予想EPS)"

    show_dividend_yield = metrics.dividend_yield is not None
    dividend_yield_label: str | None = None
    if not show_dividend_yield:
        suppressed_reasons.append("dividend_yield_unavailable")
    elif inputs.annual_dps_source == "partial":
        show_dividend_yield = False
        suppressed_reasons.append("dividend_yield_requires_full_year_dps")
    else:
        dividend_yield_label = "配当利回り"

    return ValuationNotificationPresentation(
        show_per=show_per,
        show_dividend_yield=show_dividend_yield,
        per_label=per_label,
        dividend_yield_label=dividend_yield_label,
        suppressed_reasons=tuple(dict.fromkeys(suppressed_reasons)),
        warnings=metrics.warnings,
    )
