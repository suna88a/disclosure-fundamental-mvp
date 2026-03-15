from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import ComparisonErrorReason, ComparisonStatus, RevisionDetectionStatus
from app.services.comparison_reference import ComparisonOutcome


@dataclass(frozen=True)
class SummaryBundle:
    short: str
    standard: str


def build_earnings_summary(
    progress_rate: Decimal | None,
    yoy: ComparisonOutcome,
    qoq: ComparisonOutcome,
    avg_progress: ComparisonOutcome,
    guidance_status: RevisionDetectionStatus,
    dividend_status: RevisionDetectionStatus,
) -> SummaryBundle:
    first_sentence = _build_progress_sentence(progress_rate, yoy, qoq, avg_progress)
    second_parts = [
        _guidance_display_text(guidance_status),
        _dividend_display_text(dividend_status),
    ]
    second_sentence = "、".join(part for part in second_parts if part) + "。"

    short_parts = []
    if progress_rate is not None:
        short_parts.append(f"進捗率{progress_rate}%")
    yoy_short = _comparison_short_label("前年同期比", yoy)
    if yoy_short:
        short_parts.append(yoy_short)
    guidance_short = _guidance_short_label(guidance_status)
    if guidance_short:
        short_parts.append(guidance_short)
    dividend_short = _dividend_short_label(dividend_status)
    if dividend_short:
        short_parts.append(dividend_short)

    return SummaryBundle(
        short=" / ".join(short_parts) if short_parts else "比較材料が限定的です。",
        standard=f"{first_sentence} {second_sentence}".strip(),
    )


def build_revision_only_summary(
    guidance_status: RevisionDetectionStatus,
    guidance_judgement: str | None,
    dividend_status: RevisionDetectionStatus,
    dividend_judgement: str | None,
) -> SummaryBundle:
    first_parts = []
    short_parts = []

    guidance_label = _guidance_display_text(guidance_status)
    if guidance_label:
        first_parts.append(guidance_label)
        short = _guidance_short_label(guidance_status)
        if short:
            short_parts.append(short)

    dividend_label = _dividend_display_text(dividend_status)
    if dividend_label:
        first_parts.append(dividend_label)
        short = _dividend_short_label(dividend_status)
        if short:
            short_parts.append(short)

    detail_parts = [part for part in (guidance_judgement, dividend_judgement) if part]
    standard = "、".join(first_parts) + "。"
    if detail_parts:
        standard += " " + " ".join(detail_parts)

    return SummaryBundle(
        short=" / ".join(short_parts) if short_parts else "修正内容は確認中です。",
        standard=standard.strip(),
    )


def _build_progress_sentence(
    progress_rate: Decimal | None,
    yoy: ComparisonOutcome,
    qoq: ComparisonOutcome,
    avg_progress: ComparisonOutcome,
) -> str:
    parts = []
    if progress_rate is None:
        parts.append("営業利益進捗率は算出できませんでした")
    elif progress_rate >= Decimal("80"):
        parts.append(f"営業利益進捗率は{progress_rate}%で高めです")
    elif progress_rate >= Decimal("60"):
        parts.append(f"営業利益進捗率は{progress_rate}%です")
    else:
        parts.append(f"営業利益進捗率は{progress_rate}%で低めです")

    comparison_parts = [
        _comparison_display_text("前年同期比", yoy),
        _comparison_display_text("前四半期比", qoq),
        _comparison_display_text("過去平均進捗率比", avg_progress),
    ]
    comparison_parts = [part for part in comparison_parts if part]
    if comparison_parts:
        parts.append("、".join(comparison_parts))
    return "。".join(parts).rstrip("。") + "。"


def _comparison_display_text(label: str, outcome: ComparisonOutcome) -> str:
    if outcome.status == ComparisonStatus.OK and outcome.value is not None:
        suffix = "pt" if "進捗率" in label else "%"
        sign = "+" if outcome.value >= 0 else ""
        return f"{label}は{sign}{outcome.value}{suffix}"
    reason_text = _comparison_reason_text(outcome.error_reason)
    return f"{label}は比較不可({reason_text})"


def _comparison_short_label(label: str, outcome: ComparisonOutcome) -> str | None:
    if outcome.status == ComparisonStatus.OK and outcome.value is not None:
        suffix = "pt" if "進捗率" in label else "%"
        sign = "+" if outcome.value >= 0 else ""
        return f"{label}{sign}{outcome.value}{suffix}"
    return None


def _comparison_reason_text(reason: ComparisonErrorReason) -> str:
    mapping = {
        ComparisonErrorReason.NONE: "比較可能",
        ComparisonErrorReason.INSUFFICIENT_HISTORY: "過去データ不足",
        ComparisonErrorReason.SCOPE_MISMATCH: "連結/個別不一致",
        ComparisonErrorReason.CUMULATIVE_MISMATCH: "累計/四半期不一致",
        ComparisonErrorReason.Q1_QOQ_NOT_APPLICABLE: "1Qのため前四半期比較対象外",
        ComparisonErrorReason.ACCOUNTING_STANDARD_MISMATCH: "会計基準差",
        ComparisonErrorReason.EXTRACTION_CONFIDENCE_LOW: "抽出信頼度不足",
    }
    return mapping[reason]


def _guidance_display_text(status: RevisionDetectionStatus) -> str:
    mapping = {
        RevisionDetectionStatus.UNCHANGED_DETECTED: "会社予想は据え置きです",
        RevisionDetectionStatus.NO_REVISION_DETECTED: "業績予想の修正は確認されず",
        RevisionDetectionStatus.REVISION_DETECTED_UP: "業績予想の上方修正を確認",
        RevisionDetectionStatus.REVISION_DETECTED_DOWN: "業績予想の下方修正を確認",
        RevisionDetectionStatus.REVISION_DETECTED_OTHER: "業績予想の修正を確認",
    }
    return mapping[status]


def _dividend_display_text(status: RevisionDetectionStatus) -> str:
    mapping = {
        RevisionDetectionStatus.UNCHANGED_DETECTED: "配当予想は据え置きです",
        RevisionDetectionStatus.NO_REVISION_DETECTED: "配当予想の修正は確認されず",
        RevisionDetectionStatus.REVISION_DETECTED_UP: "配当予想の増額修正を確認",
        RevisionDetectionStatus.REVISION_DETECTED_DOWN: "配当予想の減額修正を確認",
        RevisionDetectionStatus.REVISION_DETECTED_OTHER: "配当予想の修正を確認",
    }
    return mapping[status]


def _guidance_short_label(status: RevisionDetectionStatus) -> str | None:
    mapping = {
        RevisionDetectionStatus.UNCHANGED_DETECTED: "会社予想据え置き",
        RevisionDetectionStatus.NO_REVISION_DETECTED: "業績予想修正なし",
        RevisionDetectionStatus.REVISION_DETECTED_UP: "業績予想上方修正",
        RevisionDetectionStatus.REVISION_DETECTED_DOWN: "業績予想下方修正",
        RevisionDetectionStatus.REVISION_DETECTED_OTHER: "業績予想修正あり",
    }
    return mapping.get(status)


def _dividend_short_label(status: RevisionDetectionStatus) -> str | None:
    mapping = {
        RevisionDetectionStatus.UNCHANGED_DETECTED: "配当据え置き",
        RevisionDetectionStatus.NO_REVISION_DETECTED: "配当修正なし",
        RevisionDetectionStatus.REVISION_DETECTED_UP: "配当増額修正",
        RevisionDetectionStatus.REVISION_DETECTED_DOWN: "配当減額修正",
        RevisionDetectionStatus.REVISION_DETECTED_OTHER: "配当修正あり",
    }
    return mapping.get(status)
