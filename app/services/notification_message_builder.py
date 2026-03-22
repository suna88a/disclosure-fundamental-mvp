from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date

from app.models.analysis_result import AnalysisResult
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory
from app.models.notification import Notification
from app.models.valuation_view import ValuationView
from app.services.disclosure_view_service import category_label, company_display_name, format_score, format_datetime

DISCORD_MESSAGE_LIMIT = 1800
DISCORD_EMBED_DESCRIPTION_LIMIT = 3500
DISCORD_MAX_EMBEDS_PER_MESSAGE = 10
DISCORD_EMBED_TITLE_LIMIT = 250
DISCORD_EMBED_TOTAL_TEXT_LIMIT = 5500
RAW_CLASSIFICATION_PRIORITY = ["guidance", "dividend", "earnings", "other"]
RAW_DISPLAY_ORDER = ["earnings", "guidance", "dividend", "other"]
RAW_CATEGORY_LABELS = {
    "earnings": "決算短信",
    "guidance": "業績修正",
    "dividend": "配当修正",
    "other": "その他",
}
RAW_CATEGORY_COLORS = {
    "earnings": 0x3498DB,
    "guidance": 0xE67E22,
    "dividend": 0x2ECC71,
    "other": 0x95A5A6,
    "summary": 0x34495E,
}
RAW_EQUITY_EXCLUDE_KEYWORDS = (
    "ETF",
    "ETN",
    "ETP",
    "REIT",
    "インフラファンド",
    "投資法人",
    "外国投信",
    "外国投資法人",
    "上場投信",
    "上場インデックスファンド",
    "上場信託",
    "現物国内保管型",
    "SPDR",
    "ゴールド・シェア",
    "ゴールドシェア",
    "純金",
    "純プラチナ",
)
RAW_LOW_URGENCY_EXCLUDE_KEYWORDS = (
    "月次",
    "説明資料",
    "補足資料",
    "質疑応答",
    "決算説明会資料",
    "決算補足説明資料",
    "説明会資料",
    "Q&A",
    "QA",
)
RAW_SHORT_TITLE_REPLACEMENTS = (
    ("業績予想及び配当予想の修正", "業績予想・配当予想修正"),
    ("業績予想および配当予想の修正", "業績予想・配当予想修正"),
    ("連結業績予想の修正", "連結業績予想修正"),
    ("通期業績予想の修正", "通期業績予想修正"),
    ("業績予想の修正", "業績予想修正"),
    ("配当予想の修正", "配当予想修正"),
    ("特別損失の計上", "特損計上"),
    ("特別利益の計上", "特益計上"),
    ("初配当", "初配"),
)


@dataclass(frozen=True)
class RawDiscordBatch:
    disclosures: list[Disclosure]
    payload: dict[str, object]


@dataclass(frozen=True)
class _RawCategoryEmbedChunk:
    category: str
    total_count: int
    disclosures: list[Disclosure]
    description: str


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


def build_raw_discord_batches(
    *,
    disclosures: list[Disclosure],
    filtered_out_count: int,
    batch_size: int,
) -> list[RawDiscordBatch]:
    eligible = sort_raw_disclosures(filter_raw_disclosures(disclosures))
    if not eligible:
        return []

    category_chunks = _build_raw_category_embed_chunks(eligible, batch_size=batch_size)
    total_counts = _raw_category_counts(eligible)
    payloads: list[RawDiscordBatch] = []

    current_embeds: list[dict[str, object]] = [
        _build_raw_summary_embed(
            eligible_count=len(eligible),
            filtered_out_count=filtered_out_count,
            category_counts=total_counts,
        )
    ]
    current_disclosures: list[Disclosure] = []

    for chunk in category_chunks:
        embed = _build_raw_category_embed(
            chunk,
            total_parts=_category_total_parts(category_chunks, chunk.category),
            part_index=_category_part_index(category_chunks, chunk),
        )
        tentative_embeds = current_embeds + [embed]
        if current_embeds and (
            len(current_embeds) >= DISCORD_MAX_EMBEDS_PER_MESSAGE
            or _discord_embed_payload_chars(tentative_embeds) > DISCORD_EMBED_TOTAL_TEXT_LIMIT
        ):
            payloads.append(RawDiscordBatch(disclosures=current_disclosures, payload={"embeds": current_embeds}))
            current_embeds = []
            current_disclosures = []
        current_embeds.append(embed)
        current_disclosures.extend(chunk.disclosures)

    if current_embeds:
        payloads.append(RawDiscordBatch(disclosures=current_disclosures, payload={"embeds": current_embeds}))
    return payloads


def build_empty_raw_digest_discord_payload(*, target_date: date) -> dict[str, object]:
    return {
        "embeds": [
            {
                "title": "全市場 新規開示 0件",
                "description": f"{target_date.isoformat()} 17:00 JST 時点で、対象となる開示はありませんでした。",
                "color": RAW_CATEGORY_COLORS["summary"],
            }
        ]
    }


def build_empty_raw_digest_body(*, target_date: date) -> str:
    return (
        "全市場 新規開示 0件\n"
        f"{target_date.isoformat()} 17:00 JST 時点で、対象となる開示はありませんでした。"
    )


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
    has_dividend = any(keyword in normalized for keyword in ("配当予想の修正", "配当修正", "増配", "減配", "復配", "無配", "初配"))
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


def build_raw_short_title(title: str) -> str:
    shortened = unicodedata.normalize("NFKC", title).strip()
    for old, new in RAW_SHORT_TITLE_REPLACEMENTS:
        shortened = shortened.replace(old, new)
    for suffix in ("に関するお知らせ", "のお知らせ"):
        if shortened.endswith(suffix):
            shortened = shortened[: -len(suffix)]
    shortened = shortened.strip(" 　-")
    return _truncate_text(shortened or title, 48)


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


def _normalize_raw_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).upper().replace(" ", "").replace("　", "")


def _is_raw_equity_candidate(disclosure: Disclosure) -> bool:
    combined = _normalize_raw_text(" ".join(filter(None, [company_display_name(disclosure.company), disclosure.company.name, disclosure.title])))
    normalized_title = _normalize_raw_text(disclosure.title or "")
    if any(_normalize_raw_text(keyword) in combined for keyword in RAW_EQUITY_EXCLUDE_KEYWORDS):
        return False
    if any(_normalize_raw_text(keyword) in normalized_title for keyword in RAW_LOW_URGENCY_EXCLUDE_KEYWORDS):
        return False
    return True


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


def _raw_category_counts(disclosures: list[Disclosure]) -> dict[str, int]:
    counts = {category: 0 for category in RAW_DISPLAY_ORDER}
    for disclosure in disclosures:
        counts[classify_raw_disclosure(disclosure)] += 1
    return counts


def _build_raw_summary_embed(
    *,
    eligible_count: int,
    filtered_out_count: int,
    category_counts: dict[str, int],
) -> dict[str, object]:
    summary = " / ".join(
        [
            f"{RAW_CATEGORY_LABELS['earnings']} {category_counts['earnings']}",
            f"{RAW_CATEGORY_LABELS['guidance']} {category_counts['guidance']}",
            f"{RAW_CATEGORY_LABELS['dividend']} {category_counts['dividend']}",
            f"{RAW_CATEGORY_LABELS['other']} {category_counts['other']}",
            f"除外 {filtered_out_count}",
        ]
    )
    return {
        "title": f"全市場 新規開示 {eligible_count}件",
        "description": summary,
        "color": RAW_CATEGORY_COLORS["summary"],
    }


def _build_raw_category_embed_chunks(disclosures: list[Disclosure], *, batch_size: int) -> list[_RawCategoryEmbedChunk]:
    safe_batch_size = max(1, batch_size)
    chunks: list[_RawCategoryEmbedChunk] = []
    for category in RAW_DISPLAY_ORDER:
        items = [disclosure for disclosure in disclosures if classify_raw_disclosure(disclosure) == category]
        if not items:
            continue
        total_count = len(items)
        current_chunk: list[Disclosure] = []
        current_blocks: list[str] = []
        for disclosure in items:
            block = _build_raw_embed_block(disclosure)
            tentative_blocks = current_blocks + [block]
            tentative_description = "\n\n".join(tentative_blocks)
            if current_chunk and (len(tentative_description) > DISCORD_EMBED_DESCRIPTION_LIMIT or len(current_chunk) >= safe_batch_size):
                chunks.append(
                    _RawCategoryEmbedChunk(
                        category=category,
                        total_count=total_count,
                        disclosures=current_chunk,
                        description="\n\n".join(current_blocks),
                    )
                )
                current_chunk = [disclosure]
                current_blocks = [block]
            else:
                current_chunk = current_chunk + [disclosure]
                current_blocks = tentative_blocks
        if current_chunk:
            chunks.append(
                _RawCategoryEmbedChunk(
                    category=category,
                    total_count=total_count,
                    disclosures=current_chunk,
                    description="\n\n".join(current_blocks),
                )
            )
    return chunks


def _build_raw_category_embed(
    chunk: _RawCategoryEmbedChunk,
    *,
    total_parts: int,
    part_index: int,
) -> dict[str, object]:
    title = f"{RAW_CATEGORY_LABELS[chunk.category]} {chunk.total_count}件"
    if total_parts > 1:
        title = f"{title}({part_index}/{total_parts})"
    return {
        "title": _truncate_text(title, DISCORD_EMBED_TITLE_LIMIT),
        "description": chunk.description,
        "color": RAW_CATEGORY_COLORS[chunk.category],
    }


def _discord_embed_payload_chars(embeds: list[dict[str, object]]) -> int:
    total = 0
    for embed in embeds:
        title = str(embed.get("title") or "")
        description = str(embed.get("description") or "")
        total += len(title) + len(description)
    return total


def _category_total_parts(chunks: list[_RawCategoryEmbedChunk], category: str) -> int:
    return sum(1 for chunk in chunks if chunk.category == category)


def _category_part_index(chunks: list[_RawCategoryEmbedChunk], current_chunk: _RawCategoryEmbedChunk) -> int:
    same_category = [chunk for chunk in chunks if chunk.category == current_chunk.category]
    return same_category.index(current_chunk) + 1


def _build_raw_embed_block(disclosure: Disclosure) -> str:
    timestamp = format_datetime(disclosure.disclosed_at)
    company_name = company_display_name(disclosure.company)
    line1 = f"{timestamp} / {disclosure.company.code} / {company_name}"
    line2 = build_raw_short_title(disclosure.title)
    return f"{line1}\n{line2}\nPDF: <{disclosure.source_url}>"


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
