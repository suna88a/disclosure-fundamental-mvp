from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.analysis_result import AnalysisResult
from app.models.enums import (
    ComparisonErrorReason,
    ComparisonStatus,
    PdfParseErrorCode,
    PdfParseStatus,
)
from app.models.pdf_file import PdfFile
from app.services.failure_summary_report import (
    render_failure_summary,
    summarize_comparison_errors,
    summarize_pdf_parse_failures,
)


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_summarize_comparison_errors_groups_by_axis() -> None:
    session = _build_session()
    session.add_all(
        [
            AnalysisResult(
                disclosure_id=1,
                yoy_comparison_status=ComparisonStatus.NOT_COMPARABLE,
                yoy_comparison_error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
                qoq_comparison_status=ComparisonStatus.NOT_COMPARABLE,
                qoq_comparison_error_reason=ComparisonErrorReason.Q1_QOQ_NOT_APPLICABLE,
                average_progress_comparison_status=ComparisonStatus.NOT_COMPARABLE,
                average_progress_comparison_error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
                should_notify=False,
            ),
            AnalysisResult(
                disclosure_id=2,
                yoy_comparison_status=ComparisonStatus.OK,
                yoy_comparison_error_reason=ComparisonErrorReason.NONE,
                qoq_comparison_status=ComparisonStatus.NOT_COMPARABLE,
                qoq_comparison_error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
                average_progress_comparison_status=ComparisonStatus.NOT_COMPARABLE,
                average_progress_comparison_error_reason=ComparisonErrorReason.EXTRACTION_CONFIDENCE_LOW,
                should_notify=False,
            ),
        ]
    )
    session.commit()

    summary = summarize_comparison_errors(session)

    assert summary.total["insufficient_history"] == 3
    assert summary.yoy["insufficient_history"] == 1
    assert summary.qoq["q1_qoq_not_applicable"] == 1
    assert summary.average_progress["extraction_confidence_low"] == 1


def test_summarize_pdf_parse_failures_groups_normalized_reasons() -> None:
    session = _build_session()
    session.add_all(
        [
            PdfFile(
                disclosure_id=1,
                parse_status=PdfParseStatus.FAILED,
                parse_error_code=PdfParseErrorCode.UNSUPPORTED_FORMAT,
                parse_error_message="unsupported format",
            ),
            PdfFile(
                disclosure_id=2,
                parse_status=PdfParseStatus.FAILED,
                parse_error_code=PdfParseErrorCode.TIMEOUT,
                parse_error_message="Financial report extraction failed: timeout while parsing",
            ),
            PdfFile(disclosure_id=3, parse_status=PdfParseStatus.COMPLETED, parse_error_message=None),
        ]
    )
    session.commit()

    summary = summarize_pdf_parse_failures(session)
    rendered = render_failure_summary(summarize_comparison_errors(session), summary)

    assert summary.total_failed == 2
    assert summary.reasons["unsupported_format"] == 1
    assert summary.reasons["timeout"] == 1
    assert "PDF Parse Failure Summary" in rendered
