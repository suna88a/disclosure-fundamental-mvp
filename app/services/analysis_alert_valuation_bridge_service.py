from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory
from app.services.investment_input_service import get_disclosure_investment_metric_inputs
from app.services.valuation_metrics_service import build_valuation_metrics
from app.services.valuation_notification_payload_service import build_valuation_notification_draft_payload
from app.services.valuation_notification_service import build_valuation_notification_presentation
from app.services.valuation_notification_text_service import build_valuation_notification_text


@dataclass(frozen=True)
class AnalysisAlertValuationDraft:
    title: str
    valuation_lines: tuple[str, ...]
    metadata: dict[str, object]


TARGET_DISCLOSURE_CATEGORIES = {
    DisclosureCategory.GUIDANCE_REVISION,
    DisclosureCategory.DIVIDEND_REVISION,
}


def build_analysis_alert_valuation_draft(
    session: Session, disclosure: Disclosure
) -> AnalysisAlertValuationDraft | None:
    if disclosure.category not in TARGET_DISCLOSURE_CATEGORIES:
        return None

    inputs = get_disclosure_investment_metric_inputs(session, disclosure)
    metrics = build_valuation_metrics(inputs)
    presentation = build_valuation_notification_presentation(inputs, metrics)
    text = build_valuation_notification_text(
        disclosure=disclosure,
        inputs=inputs,
        metrics=metrics,
        presentation=presentation,
    )
    payload = build_valuation_notification_draft_payload(
        disclosure=disclosure,
        inputs=inputs,
        metrics=metrics,
        presentation=presentation,
        text=text,
    )
    return AnalysisAlertValuationDraft(
        title=payload.title,
        valuation_lines=tuple(text.body_lines[3:]),
        metadata=payload.metadata,
    )
