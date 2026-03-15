from app.models.analysis_result import AnalysisResult
from app.models.disclosure import Disclosure
from app.models.notification import Notification
from app.models.valuation_view import ValuationView
from app.services.disclosure_view_service import category_label, company_display_name, format_score


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
