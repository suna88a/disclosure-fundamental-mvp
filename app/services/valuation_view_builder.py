from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.models.analysis_result import AnalysisResult
from app.models.enums import (
    ComparisonStatus,
    PerDirection,
    RevisionDetectionStatus,
    ShortTermReaction,
)


@dataclass(frozen=True)
class ValuationBuildResult:
    eps_revision_potential: Decimal | None
    eps_revision_view: str
    acceptable_per_direction: PerDirection
    per_change_view: str
    short_term_reaction: ShortTermReaction
    short_term_reaction_view: str
    valuation_comment: str


def build_valuation_view(analysis: AnalysisResult) -> ValuationBuildResult:
    comparable_count = sum(
        1
        for status in (
            analysis.yoy_comparison_status,
            analysis.qoq_comparison_status,
            analysis.average_progress_comparison_status,
        )
        if status == ComparisonStatus.OK
    )
    conservative_mode = comparable_count == 0

    eps_revision_potential, eps_revision_view = _build_eps_view(analysis, conservative_mode)
    acceptable_per_direction, per_change_view = _build_per_view(analysis, conservative_mode)
    short_term_reaction, short_term_reaction_view = _build_reaction_view(
        analysis, conservative_mode
    )
    valuation_comment = _build_comment(
        analysis=analysis,
        eps_revision_view=eps_revision_view,
        per_change_view=per_change_view,
        short_term_reaction_view=short_term_reaction_view,
        conservative_mode=conservative_mode,
    )

    return ValuationBuildResult(
        eps_revision_potential=eps_revision_potential,
        eps_revision_view=eps_revision_view,
        acceptable_per_direction=acceptable_per_direction,
        per_change_view=per_change_view,
        short_term_reaction=short_term_reaction,
        short_term_reaction_view=short_term_reaction_view,
        valuation_comment=valuation_comment,
    )


def _build_eps_view(
    analysis: AnalysisResult,
    conservative_mode: bool,
) -> tuple[Decimal | None, str]:
    guidance = analysis.guidance_revision_status
    overall_score = analysis.overall_score or analysis.total_score or Decimal("0.0")

    if guidance == RevisionDetectionStatus.REVISION_DETECTED_UP:
        return Decimal("1.0000"), "EPSの上振れ余地が意識されやすい。"
    if guidance == RevisionDetectionStatus.REVISION_DETECTED_DOWN:
        return Decimal("-1.0000"), "EPSの下振れ懸念が意識されやすい。"
    if conservative_mode:
        return Decimal("0.0000"), "比較材料が限られ、EPS訂正余地は判断保留。"
    if overall_score >= Decimal("2.0"):
        return Decimal("0.5000"), "決算内容からはEPS上振れ余地を示唆。"
    if overall_score <= Decimal("-2.0"):
        return Decimal("-0.5000"), "決算内容からはEPS下振れリスクを示唆。"
    return Decimal("0.0000"), "EPS訂正余地は限定的。"


def _build_per_view(
    analysis: AnalysisResult,
    conservative_mode: bool,
) -> tuple[PerDirection, str]:
    overall_score = analysis.overall_score or analysis.total_score or Decimal("0.0")
    guidance = analysis.guidance_revision_status
    dividend = analysis.dividend_revision_status

    if conservative_mode and guidance == RevisionDetectionStatus.NO_REVISION_DETECTED:
        return PerDirection.UNKNOWN, "比較材料不足のため、許容PER方向は保留。"
    if guidance == RevisionDetectionStatus.REVISION_DETECTED_UP or dividend == RevisionDetectionStatus.REVISION_DETECTED_UP:
        return PerDirection.EXPAND, "許容PERは上方向を試す余地。"
    if guidance == RevisionDetectionStatus.REVISION_DETECTED_DOWN or overall_score <= Decimal("-2.0"):
        return PerDirection.CONTRACT, "許容PERは下方向を意識。"
    if overall_score >= Decimal("1.0"):
        return PerDirection.EXPAND, "許容PERはやや上方向。"
    return PerDirection.STABLE, "許容PERは概ね横ばい想定。"


def _build_reaction_view(
    analysis: AnalysisResult,
    conservative_mode: bool,
) -> tuple[ShortTermReaction, str]:
    overall_score = analysis.overall_score or analysis.total_score or Decimal("0.0")

    if conservative_mode and not analysis.should_notify:
        return ShortTermReaction.NEUTRAL, "比較材料が限られ、短期反応は中立寄り。"
    if analysis.should_notify and overall_score > 0:
        return ShortTermReaction.POSITIVE, "短期反応はポジティブ寄りを想定。"
    if analysis.should_notify and overall_score < 0:
        return ShortTermReaction.NEGATIVE, "短期反応はネガティブ寄りを想定。"
    return ShortTermReaction.NEUTRAL, "短期反応は限定的と想定。"


def _build_comment(
    analysis: AnalysisResult,
    eps_revision_view: str,
    per_change_view: str,
    short_term_reaction_view: str,
    conservative_mode: bool,
) -> str:
    parts = [eps_revision_view, per_change_view, short_term_reaction_view]
    if conservative_mode:
        parts.append("比較不能項目が多いため、仮説は保守的に扱う。")
    elif analysis.should_notify:
        parts.append("通知対象であり、市場評価の見直し余地を確認したい。")
    else:
        parts.append("現時点では評価見直し余地は限定的。")
    return " ".join(parts)
