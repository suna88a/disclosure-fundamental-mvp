from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.disclosure import Disclosure
from app.repositories.revision_repository import RevisionRepository
from app.services.analysis_alert_valuation_bridge_service import build_analysis_alert_valuation_draft
from app.services.disclosure_view_service import category_label, company_display_name, format_datetime, format_decimal, format_score


@dataclass(frozen=True)
class GuidanceRevisionNotificationText:
    headline: str
    body_lines: tuple[str, ...]
    metadata: dict[str, object]


def build_guidance_revision_notification_text(
    session: Session, disclosure: Disclosure
) -> GuidanceRevisionNotificationText:
    revision = RevisionRepository(session).get_guidance_revision(disclosure.id)
    headline = f"[業績修正] {disclosure.company.code} {company_display_name(disclosure.company)}"
    body_lines: list[str] = [
        f"開示種別: {category_label(disclosure.category)}",
        f"開示日時: {format_datetime(disclosure.disclosed_at)}",
        f"件名: {disclosure.title}",
    ]

    if revision is not None:
        for label, before, after, is_eps in [
            ("売上高", revision.revised_sales_before, revision.revised_sales_after, False),
            ("営業利益", revision.revised_operating_income_before, revision.revised_operating_income_after, False),
            ("経常利益", revision.revised_ordinary_income_before, revision.revised_ordinary_income_after, False),
            ("純利益", revision.revised_net_income_before, revision.revised_net_income_after, False),
            ("EPS", revision.revised_eps_before, revision.revised_eps_after, True),
        ]:
            line = _build_delta_line(label, before, after, is_eps=is_eps)
            if line is not None:
                body_lines.append(line)

    valuation_draft = build_analysis_alert_valuation_draft(session, disclosure)
    if valuation_draft is not None and valuation_draft.valuation_lines:
        body_lines.extend(valuation_draft.valuation_lines)

    return GuidanceRevisionNotificationText(
        headline=headline,
        body_lines=tuple(body_lines),
        metadata={
            "builder": "guidance_revision_notification",
            "has_guidance_revision": revision is not None,
            "valuation_metadata": valuation_draft.metadata if valuation_draft is not None else {},
        },
    )


def _build_delta_line(
    label: str,
    before: Decimal | None,
    after: Decimal | None,
    *,
    is_eps: bool,
) -> str | None:
    if before is None and after is None:
        return None
    formatter = _format_eps if is_eps else _format_amount
    if before is not None and after is not None:
        return f"{label}: {formatter(before)} -> {formatter(after)}"
    if after is not None:
        return f"{label}: 修正後 {formatter(after)}"
    return f"{label}: 修正前 {formatter(before)}"


def _format_amount(value: Decimal) -> str:
    return format_decimal(value)


def _format_eps(value: Decimal) -> str:
    return format_score(value)
