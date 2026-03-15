from decimal import Decimal

from app.models.enums import ComparisonErrorReason, ComparisonStatus, RevisionDetectionStatus
from app.services.comparison_reference import ComparisonOutcome
from app.services.summary_templates import build_earnings_summary, build_revision_only_summary


def _ok(value: str) -> ComparisonOutcome:
    return ComparisonOutcome(
        status=ComparisonStatus.OK,
        error_reason=ComparisonErrorReason.NONE,
        value=Decimal(value),
        reference_report_id=1,
        detail="ok",
    )


def _ng(reason: ComparisonErrorReason) -> ComparisonOutcome:
    return ComparisonOutcome(
        status=ComparisonStatus.NOT_COMPARABLE,
        error_reason=reason,
        value=None,
        reference_report_id=None,
        detail="ng",
    )


def test_build_earnings_summary_hides_internal_states() -> None:
    summary = build_earnings_summary(
        progress_rate=Decimal("74.1935"),
        yoy=_ng(ComparisonErrorReason.INSUFFICIENT_HISTORY),
        qoq=_ok("5.0000"),
        avg_progress=_ng(ComparisonErrorReason.EXTRACTION_CONFIDENCE_LOW),
        guidance_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
        dividend_status=RevisionDetectionStatus.UNCHANGED_DETECTED,
    )

    assert "no_revision_detected" not in summary.short
    assert "unchanged_detected" not in summary.standard
    assert "業績予想の修正は確認されず" in summary.standard
    assert "配当予想は据え置きです" in summary.standard


def test_build_revision_only_summary_uses_natural_japanese() -> None:
    summary = build_revision_only_summary(
        guidance_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
        guidance_judgement="業績予想は上方修正を検知。 営業利益修正率 11.9%。",
        dividend_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
        dividend_judgement=None,
    )

    assert summary.short == "業績予想上方修正 / 配当修正なし"
    assert "業績予想の上方修正を確認" in summary.standard
    assert "配当予想の修正は確認されず" in summary.standard
