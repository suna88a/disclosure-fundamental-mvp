from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.models.dividend_revision import DividendRevision
from app.models.enums import ComparisonStatus, RevisionDetectionStatus, ToneJudgement
from app.models.financial_report import FinancialReport
from app.models.guidance_revision import GuidanceRevision
from app.services.comparison_reference import ComparisonOutcome
from app.services.summary_templates import build_earnings_summary


@dataclass(frozen=True)
class AnalysisBuildResult:
    progress_judgement: str
    guidance_revision_status: RevisionDetectionStatus
    guidance_revision_judgement: str
    dividend_revision_status: RevisionDetectionStatus
    dividend_revision_judgement: str
    overall_score: Decimal
    should_notify: bool
    short_summary: str
    tone_judgement: ToneJudgement | None


def build_analysis_result(
    report: FinancialReport,
    yoy: ComparisonOutcome,
    qoq: ComparisonOutcome,
    avg_progress: ComparisonOutcome,
    guidance_revision: GuidanceRevision | None,
    dividend_revision: DividendRevision | None,
) -> AnalysisBuildResult:
    progress_judgement, progress_score = _build_progress_judgement(report, yoy, qoq, avg_progress)
    guidance_status, guidance_judgement, guidance_score, guidance_notify = _build_guidance_status(
        report, guidance_revision
    )
    dividend_status, dividend_judgement, dividend_score, dividend_notify = _build_dividend_status(
        dividend_revision
    )

    overall_score = progress_score + guidance_score + dividend_score
    should_notify = guidance_notify or dividend_notify or overall_score >= Decimal("2.0")

    summary_bundle = build_earnings_summary(
        progress_rate=report.progress_rate_operating_income,
        yoy=yoy,
        qoq=qoq,
        avg_progress=avg_progress,
        guidance_status=guidance_status,
        dividend_status=dividend_status,
    )

    tone: ToneJudgement | None = None
    if overall_score > 0:
        tone = ToneJudgement.POSITIVE
    elif overall_score < 0:
        tone = ToneJudgement.NEGATIVE
    elif any(
        outcome.status == ComparisonStatus.OK for outcome in (yoy, qoq, avg_progress)
    ) or guidance_status != RevisionDetectionStatus.NO_REVISION_DETECTED:
        tone = ToneJudgement.NEUTRAL

    return AnalysisBuildResult(
        progress_judgement=progress_judgement,
        guidance_revision_status=guidance_status,
        guidance_revision_judgement=guidance_judgement,
        dividend_revision_status=dividend_status,
        dividend_revision_judgement=dividend_judgement,
        overall_score=overall_score,
        should_notify=should_notify,
        short_summary=summary_bundle.short,
        tone_judgement=tone,
    )


def _build_progress_judgement(
    report: FinancialReport,
    yoy: ComparisonOutcome,
    qoq: ComparisonOutcome,
    avg_progress: ComparisonOutcome,
) -> tuple[str, Decimal]:
    progress = report.progress_rate_operating_income
    if progress is None:
        base = "営業利益進捗率は算出不可。"
        score = Decimal("0.0")
    elif progress >= Decimal("80"):
        base = f"営業利益進捗率は {progress}% で高め。"
        score = Decimal("1.0")
    elif progress >= Decimal("60"):
        base = f"営業利益進捗率は {progress}% 。"
        score = Decimal("0.3")
    else:
        base = f"営業利益進捗率は {progress}% で低め。"
        score = Decimal("-0.5")

    comparison_parts = [
        _comparison_phrase("前年同期比", yoy),
        _comparison_phrase("前四半期比", qoq),
        _comparison_phrase("過去平均進捗率比", avg_progress),
    ]
    return f"{base} {' '.join(comparison_parts)}".strip(), score + _comparison_score(yoy, qoq, avg_progress)


def _build_guidance_status(
    report: FinancialReport,
    guidance_revision: GuidanceRevision | None,
) -> tuple[RevisionDetectionStatus, str, Decimal, bool]:
    if guidance_revision is None:
        if report.company_forecast_operating_income is not None:
            return (
                RevisionDetectionStatus.NO_REVISION_DETECTED,
                "会社予想は取得できているが、修正開示は未検知。",
                Decimal("0.0"),
                False,
            )
        return (
            RevisionDetectionStatus.NO_REVISION_DETECTED,
            "会社予想と修正開示の両方が未取得のため、判定保留。",
            Decimal("0.0"),
            False,
        )

    direction = guidance_revision.revision_direction
    rate = guidance_revision.revision_rate_operating_income
    rate_text = f" 営業利益修正率 {rate}%." if rate is not None else ""
    if direction and direction.value == "up":
        return (
            RevisionDetectionStatus.REVISION_DETECTED_UP,
            f"業績予想は上方修正を検知。{rate_text}".strip(),
            Decimal("2.0"),
            True,
        )
    if direction and direction.value == "down":
        return (
            RevisionDetectionStatus.REVISION_DETECTED_DOWN,
            f"業績予想は下方修正を検知。{rate_text}".strip(),
            Decimal("-2.0"),
            True,
        )
    if direction and direction.value == "unchanged":
        return (
            RevisionDetectionStatus.UNCHANGED_DETECTED,
            "業績予想は据え置き開示を検知。",
            Decimal("0.0"),
            False,
        )
    return (
        RevisionDetectionStatus.REVISION_DETECTED_OTHER,
        "業績予想修正は検知したが、方向判定は保留。",
        Decimal("0.0"),
        True,
    )


def _build_dividend_status(
    dividend_revision: DividendRevision | None,
) -> tuple[RevisionDetectionStatus, str, Decimal, bool]:
    if dividend_revision is None:
        return (
            RevisionDetectionStatus.NO_REVISION_DETECTED,
            "配当修正は未検知。",
            Decimal("0.0"),
            False,
        )

    direction = dividend_revision.revision_direction
    annual_before = dividend_revision.annual_dividend_before
    annual_after = dividend_revision.annual_dividend_after
    annual_text = ""
    if annual_before is not None or annual_after is not None:
        annual_text = f" 年間配当 {annual_before}円 -> {annual_after}円。"

    if direction and direction.value == "up":
        return (
            RevisionDetectionStatus.REVISION_DETECTED_UP,
            f"配当は増額修正を検知。{annual_text}".strip(),
            Decimal("1.5"),
            True,
        )
    if direction and direction.value == "down":
        return (
            RevisionDetectionStatus.REVISION_DETECTED_DOWN,
            f"配当は減額修正を検知。{annual_text}".strip(),
            Decimal("-1.5"),
            True,
        )
    if direction and direction.value == "unchanged":
        return (
            RevisionDetectionStatus.UNCHANGED_DETECTED,
            "配当は据え置き開示を検知。",
            Decimal("0.0"),
            False,
        )
    return (
        RevisionDetectionStatus.REVISION_DETECTED_OTHER,
        "配当修正は検知したが、方向判定は保留。",
        Decimal("0.0"),
        True,
    )


def _comparison_phrase(label: str, outcome: ComparisonOutcome) -> str:
    if outcome.status == ComparisonStatus.OK and outcome.value is not None:
        sign = "+" if outcome.value >= 0 else ""
        suffix = "pt" if "進捗率" in label else "%"
        return f"{label}{sign}{outcome.value}{suffix}。"
    return f"{label}は比較不能({outcome.error_reason.value})。"


def _comparison_score(*outcomes: ComparisonOutcome) -> Decimal:
    score = Decimal("0.0")
    for outcome in outcomes:
        if outcome.status != ComparisonStatus.OK or outcome.value is None:
            continue
        if outcome.value > 0:
            score += Decimal("0.5")
        elif outcome.value < 0:
            score -= Decimal("0.5")
    return score
