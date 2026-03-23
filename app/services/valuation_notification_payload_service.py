from __future__ import annotations

from dataclasses import dataclass

from app.models.disclosure import Disclosure
from app.services.disclosure_view_service import category_label, company_display_name
from app.services.investment_input_service import InvestmentMetricInputs
from app.services.valuation_metrics_service import ValuationMetrics
from app.services.valuation_notification_service import ValuationNotificationPresentation
from app.services.valuation_notification_text_service import ValuationNotificationText


@dataclass(frozen=True)
class ValuationNotificationDraftPayload:
    title: str
    body: str
    metadata: dict[str, object]


def build_valuation_notification_draft_payload(
    *,
    disclosure: Disclosure,
    inputs: InvestmentMetricInputs,
    metrics: ValuationMetrics,
    presentation: ValuationNotificationPresentation,
    text: ValuationNotificationText,
) -> ValuationNotificationDraftPayload:
    title = f"[{category_label(disclosure.category)}] {disclosure.company.code} {company_display_name(disclosure.company)}"
    body = "\n".join(text.body_lines)
    metadata = {
        "disclosure_id": disclosure.id,
        "company_code": disclosure.company.code,
        "category": disclosure.category.value if disclosure.category is not None else None,
        "shown_fields": list(text.shown_fields),
        "omitted_fields": list(text.omitted_fields),
        "suppressed_reasons": list(presentation.suppressed_reasons),
        "warnings": list(presentation.warnings),
    }
    return ValuationNotificationDraftPayload(title=title, body=body, metadata=metadata)
