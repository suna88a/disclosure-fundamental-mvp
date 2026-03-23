from __future__ import annotations

from dataclasses import dataclass

from app.models.disclosure import Disclosure
from app.services.disclosure_view_service import company_display_name, format_datetime, format_score, category_label
from app.services.investment_input_service import InvestmentMetricInputs
from app.services.valuation_metrics_service import ValuationMetrics
from app.services.valuation_notification_service import ValuationNotificationPresentation


@dataclass(frozen=True)
class ValuationNotificationText:
    headline: str
    body_lines: tuple[str, ...]
    shown_fields: tuple[str, ...]
    omitted_fields: tuple[str, ...]


def build_valuation_notification_text(
    *,
    disclosure: Disclosure,
    inputs: InvestmentMetricInputs,
    metrics: ValuationMetrics,
    presentation: ValuationNotificationPresentation,
) -> ValuationNotificationText:
    headline = f"{disclosure.company.code} {company_display_name(disclosure.company)}"
    body_lines: list[str] = [
        f"開示種別: {category_label(disclosure.category)}",
        f"開示日時: {format_datetime(disclosure.disclosed_at)}",
        f"件名: {disclosure.title}",
    ]
    shown_fields: list[str] = []
    omitted_fields: list[str] = []

    if presentation.show_per and metrics.forward_per is not None and presentation.per_label:
        body_lines.append(f"{presentation.per_label}: {format_score(metrics.forward_per)}")
        shown_fields.append("per")
    else:
        omitted_fields.append("per")

    if presentation.show_dividend_yield and metrics.dividend_yield is not None and presentation.dividend_yield_label:
        yield_percent = metrics.dividend_yield * 100
        body_lines.append(f"{presentation.dividend_yield_label}: {yield_percent:.1f}%")
        shown_fields.append("dividend_yield")
    else:
        omitted_fields.append("dividend_yield")

    return ValuationNotificationText(
        headline=headline,
        body_lines=tuple(body_lines),
        shown_fields=tuple(shown_fields),
        omitted_fields=tuple(omitted_fields),
    )
