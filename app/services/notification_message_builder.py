from __future__ import annotations

from app.models.analysis_result import AnalysisResult
from app.models.disclosure import Disclosure
from app.models.notification import Notification
from app.models.valuation_view import ValuationView
from app.services.disclosure_view_service import category_label, company_display_name, format_score, format_datetime

DISCORD_MESSAGE_LIMIT = 1800


def build_notification_body(
    *,
    disclosure: Disclosure,
    analysis: AnalysisResult,
    valuation: ValuationView | None,
    web_base_url: str,
) -> str:
    company = disclosure.company
    category = category_label(disclosure.category)
    summary = analysis.auto_summary or "要点は確認中です。"
    valuation_line = _valuation_line(valuation)
    score_line = f"総合スコア: {format_score(analysis.overall_score)}\n" if analysis.overall_score is not None else ""
    detail_url = f"{web_base_url.rstrip('/')}/disclosures/{disclosure.id}"

    return (
        f"{company.code} {company_display_name(company)}\n"
        f"開示種別: {category}\n"
        f"要点: {summary}\n"
        f"{valuation_line}\n"
        f"{score_line}"
        f"詳細: {detail_url}"
    ).strip()


def build_raw_disclosure_batches(
    *,
    disclosures: list[Disclosure],
    batch_size: int,
    max_chars: int = DISCORD_MESSAGE_LIMIT,
) -> list[tuple[list[Disclosure], str]]:
    if batch_size < 1:
        batch_size = 1

    blocks: list[tuple[Disclosure, str]] = [
        (disclosure, _build_raw_disclosure_block(disclosure)) for disclosure in disclosures
    ]
    batches: list[tuple[list[Disclosure], str]] = []
    current_items: list[Disclosure] = []
    current_blocks: list[str] = []

    for disclosure, block in blocks:
        tentative_items = current_items + [disclosure]
        tentative_blocks = current_blocks + [block]
        if current_blocks and (
            len(tentative_items) > batch_size or len(_render_raw_disclosure_batch(tentative_blocks)) > max_chars
        ):
            batches.append((current_items, _render_raw_disclosure_batch(current_blocks)))
            current_items = [disclosure]
            current_blocks = [block]
            continue

        if not current_blocks and len(_render_raw_disclosure_batch([block])) > max_chars:
            truncated = _truncate_text(block, max_chars - 40)
            current_items = [disclosure]
            current_blocks = [truncated]
            batches.append((current_items, _render_raw_disclosure_batch(current_blocks)))
            current_items = []
            current_blocks = []
            continue

        current_items = tentative_items
        current_blocks = tentative_blocks

    if current_blocks:
        batches.append((current_items, _render_raw_disclosure_batch(current_blocks)))
    return batches


def build_dedupe_key(
    *,
    disclosure_id: int,
    notification_type: str,
    channel: str,
    destination: str,
) -> str:
    return f"{disclosure_id}:{notification_type}:{channel}:{destination}"


def _valuation_line(valuation: ValuationView | None) -> str:
    if valuation is None:
        return "見立て: 評価見直しの仮説はまだ生成されていません。"
    if valuation.valuation_comment:
        return f"見立て: {valuation.valuation_comment}"
    if valuation.short_term_reaction_view and valuation.eps_revision_view:
        return f"見立て: {valuation.eps_revision_view} {valuation.short_term_reaction_view}"
    if valuation.valuation_comment:
        return f"見立て: {valuation.valuation_comment}"
    return "見立て: 材料が限られるため、評価見直しは保守的に見ています。"


def _build_raw_disclosure_block(disclosure: Disclosure) -> str:
    timestamp = format_datetime(disclosure.disclosed_at)
    company = f"{disclosure.company.code} {company_display_name(disclosure.company)}"
    title = _truncate_text(disclosure.title, 220)
    return f"{timestamp} | {company}\n{title}\n{disclosure.source_url}"


def _render_raw_disclosure_batch(blocks: list[str]) -> str:
    return f"【全市場 新規開示】{len(blocks)}件\n\n" + "\n\n".join(blocks)


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
