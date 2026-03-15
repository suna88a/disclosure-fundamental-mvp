from decimal import Decimal

from app.models.analysis_result import AnalysisResult
from app.models.enums import (
    ComparisonErrorReason,
    ComparisonStatus,
    PerDirection,
    RevisionDetectionStatus,
    ShortTermReaction,
)
from app.services.valuation_view_builder import build_valuation_view


def test_valuation_view_builder_positive_case() -> None:
    analysis = AnalysisResult(
        disclosure_id=1,
        guidance_revision_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
        dividend_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
        overall_score=Decimal("3.0"),
        should_notify=True,
        yoy_comparison_status=ComparisonStatus.OK,
        yoy_comparison_error_reason=ComparisonErrorReason.NONE,
        qoq_comparison_status=ComparisonStatus.OK,
        qoq_comparison_error_reason=ComparisonErrorReason.NONE,
        average_progress_comparison_status=ComparisonStatus.OK,
        average_progress_comparison_error_reason=ComparisonErrorReason.NONE,
    )

    built = build_valuation_view(analysis)

    assert built.eps_revision_potential == Decimal("1.0000")
    assert built.acceptable_per_direction == PerDirection.EXPAND
    assert built.short_term_reaction == ShortTermReaction.POSITIVE
    assert "EPSの上振れ余地" in built.valuation_comment


def test_valuation_view_builder_conservative_case() -> None:
    analysis = AnalysisResult(
        disclosure_id=2,
        guidance_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
        dividend_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
        overall_score=Decimal("0.3"),
        should_notify=False,
        yoy_comparison_status=ComparisonStatus.NOT_COMPARABLE,
        yoy_comparison_error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
        qoq_comparison_status=ComparisonStatus.NOT_COMPARABLE,
        qoq_comparison_error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
        average_progress_comparison_status=ComparisonStatus.NOT_COMPARABLE,
        average_progress_comparison_error_reason=ComparisonErrorReason.EXTRACTION_CONFIDENCE_LOW,
    )

    built = build_valuation_view(analysis)

    assert built.acceptable_per_direction == PerDirection.UNKNOWN
    assert built.short_term_reaction == ShortTermReaction.NEUTRAL
    assert "保守的" in built.valuation_comment
