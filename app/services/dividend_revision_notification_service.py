from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.disclosure import Disclosure
from app.repositories.revision_repository import RevisionRepository
from app.services.analysis_alert_valuation_bridge_service import build_analysis_alert_valuation_draft
from app.services.disclosure_view_service import category_label, company_display_name, format_datetime, format_score


@dataclass(frozen=True)
class DividendRevisionNotificationText:
    headline: str
    body_lines: tuple[str, ...]
    metadata: dict[str, object]


def build_dividend_revision_notification_text(
    session: Session, disclosure: Disclosure
) -> DividendRevisionNotificationText:
    revision = RevisionRepository(session).get_dividend_revision(disclosure.id)
    headline = f"[配当修正] {disclosure.company.code} {company_display_name(disclosure.company)}"
    body_lines: list[str] = [
        f"開示種別: {category_label(disclosure.category)}",
        f"開示日時: {format_datetime(disclosure.disclosed_at)}",
        f"件名: {disclosure.title}",
    ]

    if revision is not None:
        for label, before, after in [
            ("中間配当", revision.interim_dividend_before, revision.interim_dividend_after),
            ("期末配当", revision.year_end_dividend_before, revision.year_end_dividend_after),
            ("年間配当", revision.annual_dividend_before, revision.annual_dividend_after),
        ]:
            line = _build_delta_line(label, before, after)
            if line is not None:
                body_lines.append(line)

    valuation_draft = build_analysis_alert_valuation_draft(session, disclosure)
    if valuation_draft is not None and valuation_draft.valuation_lines:
        body_lines.extend(valuation_draft.valuation_lines)

    return DividendRevisionNotificationText(
        headline=headline,
        body_lines=tuple(body_lines),
        metadata={
            "builder": "dividend_revision_notification",
            "has_dividend_revision": revision is not None,
            "valuation_metadata": valuation_draft.metadata if valuation_draft is not None else {},
        },
    )


def _build_delta_line(label: str, before: Decimal | None, after: Decimal | None) -> str | None:
    if before is None and after is None:
        return None
    if before is not None and after is not None:
        return f"{label}: {_format_dividend(before)} -> {_format_dividend(after)}"
    if after is not None:
        return f"{label}: 修正後 {_format_dividend(after)}"
    return f"{label}: 修正前 {_format_dividend(before)}"


def _format_dividend(value: Decimal) -> str:
    return format_score(value)
