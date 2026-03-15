from datetime import datetime
from decimal import Decimal

from app.models.dividend_revision import DividendRevision
from app.models.enums import (
    ComparisonErrorReason,
    ComparisonStatus,
    CumulativeType,
    PeriodType,
    RevisionDetectionStatus,
    RevisionDirection,
    StatementScope,
)
from app.models.financial_report import FinancialReport
from app.services.analysis_result_builder import build_analysis_result
from app.services.comparison_reference import ComparisonOutcome


def _report() -> FinancialReport:
    return FinancialReport(
        disclosure_id=1,
        accounting_standard="JGAAP",
        period_type=PeriodType.Q3,
        statement_scope=StatementScope.CONSOLIDATED,
        cumulative_type=CumulativeType.CUMULATIVE,
        operating_income=Decimal("120"),
        company_forecast_operating_income=Decimal("150"),
        progress_rate_operating_income=Decimal("80.0000"),
        extraction_confidence=Decimal("0.95"),
        extraction_version="v1",
    )


def _ok_outcome(value: str, detail: str) -> ComparisonOutcome:
    return ComparisonOutcome(
        status=ComparisonStatus.OK,
        error_reason=ComparisonErrorReason.NONE,
        value=Decimal(value),
        reference_report_id=1,
        detail=detail,
    )


def test_analysis_builder_distinguishes_no_revision_detected() -> None:
    result = build_analysis_result(
        report=_report(),
        yoy=_ok_outcome("10.0", "YoY"),
        qoq=_ok_outcome("5.0", "QoQ"),
        avg_progress=_ok_outcome("4.0", "AVG"),
        guidance_revision=None,
        dividend_revision=None,
    )

    assert result.guidance_revision_status == RevisionDetectionStatus.NO_REVISION_DETECTED
    assert result.dividend_revision_status == RevisionDetectionStatus.NO_REVISION_DETECTED
    assert "業績予想修正なし" in result.short_summary
    assert "配当修正なし" in result.short_summary


def test_analysis_builder_detects_unchanged_and_downward() -> None:
    result = build_analysis_result(
        report=_report(),
        yoy=ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
            value=None,
            reference_report_id=None,
            detail="YoY unavailable",
        ),
        qoq=ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.Q1_QOQ_NOT_APPLICABLE,
            value=None,
            reference_report_id=None,
            detail="QoQ unavailable",
        ),
        avg_progress=ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
            value=None,
            reference_report_id=None,
            detail="AVG unavailable",
        ),
        guidance_revision=None,
        dividend_revision=DividendRevision(
            disclosure_id=1,
            annual_dividend_before=Decimal("100"),
            annual_dividend_after=Decimal("90"),
            revision_direction=RevisionDirection.DOWN,
        ),
    )

    assert result.dividend_revision_status == RevisionDetectionStatus.REVISION_DETECTED_DOWN
    assert result.should_notify is True
    assert "配当減額修正" in result.short_summary
