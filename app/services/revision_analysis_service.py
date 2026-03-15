from __future__ import annotations

from decimal import Decimal

from app.fetchers.revision_extractor import DividendRevisionPayload, GuidanceRevisionPayload
from app.models.enums import RevisionDetectionStatus, RevisionDirection, ToneJudgement
from app.services.summary_templates import build_revision_only_summary


def build_guidance_judgement(payload: GuidanceRevisionPayload) -> tuple[str, Decimal, bool]:
    direction = payload.revision_direction or RevisionDirection.NOT_AVAILABLE
    rate = payload.revision_rate_operating_income
    score = Decimal("0.0")
    should_notify = True

    if direction == RevisionDirection.UP:
        score = Decimal("2.0")
        detail = "業績予想は上方修正を検知。"
    elif direction == RevisionDirection.DOWN:
        score = Decimal("-2.0")
        detail = "業績予想は下方修正を検知。"
    elif direction == RevisionDirection.UNCHANGED:
        score = Decimal("0.0")
        detail = "業績予想は据え置き開示を検知。"
        should_notify = False
    else:
        detail = "業績予想修正は検知したが、方向判定は保留。"

    if rate is not None:
        detail += f" 営業利益修正率 {rate}%。"

    return detail, score, should_notify


def build_dividend_judgement(payload: DividendRevisionPayload) -> tuple[str, Decimal, bool]:
    direction = payload.revision_direction or RevisionDirection.NOT_AVAILABLE
    score = Decimal("0.0")
    should_notify = True

    if direction == RevisionDirection.UP:
        score = Decimal("1.5")
        detail = "配当は増額修正を検知。"
    elif direction == RevisionDirection.DOWN:
        score = Decimal("-1.5")
        detail = "配当は減額修正を検知。"
    elif direction == RevisionDirection.UNCHANGED:
        detail = "配当は据え置き開示を検知。"
        should_notify = False
    else:
        detail = "配当修正は検知したが、方向判定は保留。"

    annual_before = payload.annual_dividend_before
    annual_after = payload.annual_dividend_after
    if annual_before is not None or annual_after is not None:
        detail += f" 年間配当 {annual_before}円 -> {annual_after}円。"

    return detail, score, should_notify


def build_analysis_payload(
    guidance_payload: GuidanceRevisionPayload | None,
    dividend_payload: DividendRevisionPayload | None,
    extraction_reason: str,
) -> dict[str, object]:
    guidance_judgement = None
    dividend_judgement = None
    summary_parts = []
    total_score = Decimal("0.0")
    should_notify = False
    tone = ToneJudgement.UNKNOWN

    if guidance_payload is not None:
        guidance_judgement, score, guidance_notify = build_guidance_judgement(guidance_payload)
        summary_parts.append(guidance_judgement)
        total_score += score
        should_notify = should_notify or guidance_notify

    if dividend_payload is not None:
        dividend_judgement, score, dividend_notify = build_dividend_judgement(dividend_payload)
        summary_parts.append(dividend_judgement)
        total_score += score
        should_notify = should_notify or dividend_notify

    if total_score > 0:
        tone = ToneJudgement.POSITIVE
    elif total_score < 0:
        tone = ToneJudgement.NEGATIVE
    elif summary_parts:
        tone = ToneJudgement.NEUTRAL

    summary_bundle = build_revision_only_summary(
        guidance_status=_guidance_status(guidance_payload),
        guidance_judgement=guidance_judgement,
        dividend_status=_dividend_status(dividend_payload),
        dividend_judgement=dividend_judgement,
    )
    auto_summary = summary_bundle.short if summary_parts else extraction_reason

    return {
        "progress_judgement": "Not evaluated for standalone revision disclosure.",
        "guidance_revision_status": _guidance_status(guidance_payload),
        "guidance_revision_judgement": guidance_judgement,
        "dividend_revision_status": _dividend_status(dividend_payload),
        "dividend_revision_judgement": dividend_judgement,
        "comment_tone": tone,
        "auto_summary": auto_summary,
        "overall_score": total_score,
        "total_score": total_score,
        "should_notify": should_notify,
    }


def _guidance_status(payload: GuidanceRevisionPayload | None) -> RevisionDetectionStatus:
    if payload is None:
        return RevisionDetectionStatus.NO_REVISION_DETECTED
    direction = payload.revision_direction
    if direction == RevisionDirection.UP:
        return RevisionDetectionStatus.REVISION_DETECTED_UP
    if direction == RevisionDirection.DOWN:
        return RevisionDetectionStatus.REVISION_DETECTED_DOWN
    if direction == RevisionDirection.UNCHANGED:
        return RevisionDetectionStatus.UNCHANGED_DETECTED
    return RevisionDetectionStatus.REVISION_DETECTED_OTHER


def _dividend_status(payload: DividendRevisionPayload | None) -> RevisionDetectionStatus:
    if payload is None:
        return RevisionDetectionStatus.NO_REVISION_DETECTED
    direction = payload.revision_direction
    if direction == RevisionDirection.UP:
        return RevisionDetectionStatus.REVISION_DETECTED_UP
    if direction == RevisionDirection.DOWN:
        return RevisionDetectionStatus.REVISION_DETECTED_DOWN
    if direction == RevisionDirection.UNCHANGED:
        return RevisionDetectionStatus.UNCHANGED_DETECTED
    return RevisionDetectionStatus.REVISION_DETECTED_OTHER
