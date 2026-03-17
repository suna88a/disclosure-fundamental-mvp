from __future__ import annotations

from app.models.analysis_result import AnalysisResult
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory
from app.models.notification import Notification
from app.models.valuation_view import ValuationView
from app.services.disclosure_view_service import category_label, company_display_name, format_score, format_datetime

DISCORD_MESSAGE_LIMIT = 1800
RAW_CLASSIFICATION_PRIORITY = ["guidance", "dividend", "earnings", "other"]
RAW_DISPLAY_ORDER = ["earnings", "guidance", "dividend", "other"]
RAW_CATEGORY_LABELS = {
    "earnings": "決算短信",
    "guidance": "業績修正",
    "dividend": "配当修正",
    "other": "その他",
}
RAW_EQUITY_EXCLUDE_KEYWORDS = (
    "ETF",
    "ETN",
    "REIT",
    "インフラファンド",
    "投資法人",
    "外国投信",
    "外国投資法人",
    "上場投信",
    "上場インデックスファンド",
)


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

    eligible = sort_raw_disclosures(filter_raw_disclosures(disclosures))
    if not eligible:
        return []

    batches: list[tuple[list[Disclosure], str]] = []
    current_items: list[Disclosure] = []

    for disclosure in eligible:
        tentative_items = current_items + [disclosure]
        tentative_body = _render_raw_disclosure_batch(tentative_items)
        if current_items and (len(tentative_items) > batch_size or len(tentative_body) > max_chars):
            batches.append((current_items, _render_raw_disclosure_batch(current_items)))
            current_items = [disclosure]
            continue

        if not current_items and len(tentative_body) > max_chars:
            single_body = _render_raw_disclosure_batch([disclosure])
            batches.append(([disclosure], _truncate_text(single_body, max_chars)))
            current_items = []
            continue

        current_items = tentative_items

    if current_items:
        batches.append((current_items, _render_raw_disclosure_batch(current_items)))
    return batches


def filter_raw_disclosures(disclosures: list[Disclosure]) -> list[Disclosure]:
    return [disclosure for disclosure in disclosures if _is_raw_equity_candidate(disclosure)]


def sort_raw_disclosures(disclosures: list[Disclosure]) -> list[Disclosure]:
    return sorted(
        disclosures,
        key=lambda disclosure: (RAW_DISPLAY_ORDER.index(classify_raw_disclosure(disclosure)), disclosure.disclosed_at, disclosure.id),
        reverse=False,
    )


def classify_raw_disclosure(disclosure: Disclosure) -> str:
    title = disclosure.title or ""
    normalized = title.replace(" ", "")
    has_dividend = any(keyword in normalized for keyword in ("配当予想の修正", "配当修正", "増配", "減配", "復配", "無配"))
    has_guidance = any(keyword in normalized for keyword in ("業績予想", "通期予想", "連結業績予想", "業績修正"))

    if has_guidance:
        return "guidance"
    if has_dividend:
        return "dividend"
    if disclosure.category == DisclosureCategory.EARNINGS_REPORT or "決算短信" in normalized:
        return "earnings"
    return "other"


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


def _is_raw_equity_candidate(disclosure: Disclosure) -> bool:
    combined = " ".join(filter(None, [company_display_name(disclosure.company), disclosure.company.name, disclosure.title])).upper()
    return not any(keyword.upper() in combined for keyword in RAW_EQUITY_EXCLUDE_KEYWORDS)


def _build_raw_disclosure_block(disclosure: Disclosure) -> str:
    timestamp = format_datetime(disclosure.disclosed_at)
    company = f"{disclosure.company.code} {company_display_name(disclosure.company)}"
    title = _truncate_text(disclosure.title, 220)
    return f"- {timestamp} | {company}\n  {title}\n  {disclosure.source_url}"


def _render_raw_disclosure_batch(disclosures: list[Disclosure]) -> str:
    sections: list[str] = []
    for category in RAW_DISPLAY_ORDER:
        items = [disclosure for disclosure in disclosures if classify_raw_disclosure(disclosure) == category]
        if not items:
            continue
        blocks = "\n".join(_build_raw_disclosure_block(disclosure) for disclosure in items)
        sections.append(f"【{RAW_CATEGORY_LABELS[category]} {len(items)}件】\n{blocks}")
    return f"【全市場 新規開示】{len(disclosures)}件\n\n" + "\n\n".join(sections)


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
