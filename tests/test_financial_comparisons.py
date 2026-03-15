from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import (
    ComparisonErrorReason,
    ComparisonStatus,
    CumulativeType,
    DisclosureCategory,
    DisclosurePriority,
    PdfDownloadStatus,
    PdfParseStatus,
    PeriodType,
    RevisionDetectionStatus,
    RevisionDirection,
    StatementScope,
)
from app.models.financial_report import FinancialReport
from app.models.guidance_revision import GuidanceRevision
from app.models.pdf_file import PdfFile
from app.services.financial_comparison_ingestion import ingest_financial_comparisons


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _create_report(
    session: Session,
    company: Company,
    disclosed_at: str,
    period_type: PeriodType,
    operating_income: Decimal,
    forecast_operating_income: Decimal,
    progress_rate: Decimal | None,
    extraction_confidence: Decimal,
    cumulative_type: CumulativeType = CumulativeType.CUMULATIVE,
    statement_scope: StatementScope = StatementScope.CONSOLIDATED,
    accounting_standard: str = "JGAAP",
) -> FinancialReport:
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat(disclosed_at),
        title=f"Earnings {period_type.value} {disclosed_at}",
        normalized_title="earnings report",
        category=DisclosureCategory.EARNINGS_REPORT,
        priority=DisclosurePriority.CRITICAL,
        source_url=f"https://example.com/{company.code}/{period_type.value}/{disclosed_at}",
        source_disclosure_id=f"{company.code}-{period_type.value}-{disclosed_at}",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    pdf_file = PdfFile(
        disclosure_id=disclosure.id,
        source_url=f"data/samples/{disclosure.id}.pdf",
        file_path=f"data/samples/{disclosure.id}.pdf",
        file_hash=f"hash-{disclosure.id}",
        download_status=PdfDownloadStatus.DOWNLOADED,
        parse_status=PdfParseStatus.COMPLETED,
    )
    session.add(pdf_file)
    session.flush()
    report = FinancialReport(
        disclosure_id=disclosure.id,
        pdf_file_id=pdf_file.id,
        accounting_standard=accounting_standard,
        period_type=period_type,
        statement_scope=statement_scope,
        cumulative_type=cumulative_type,
        sales=Decimal("1000"),
        operating_income=operating_income,
        ordinary_income=operating_income,
        net_income=operating_income,
        eps=Decimal("10"),
        company_forecast_sales=Decimal("2000"),
        company_forecast_operating_income=forecast_operating_income,
        company_forecast_ordinary_income=forecast_operating_income,
        company_forecast_net_income=forecast_operating_income,
        company_forecast_eps=Decimal("20"),
        progress_rate_operating_income=progress_rate,
        extraction_confidence=extraction_confidence,
        extraction_version="v1",
    )
    session.add(report)
    session.flush()
    return report


def test_financial_comparisons_compute_progress_and_statuses() -> None:
    session = _build_session()
    company = Company(code="6758", name="Sony")
    session.add(company)
    session.flush()

    _create_report(
        session, company, "2024-02-01T15:00:00+09:00", PeriodType.Q3, Decimal("100"), Decimal("140"), Decimal("71.4286"), Decimal("0.95")
    )
    _create_report(
        session, company, "2025-02-01T15:00:00+09:00", PeriodType.Q3, Decimal("110"), Decimal("145"), Decimal("75.8621"), Decimal("0.95")
    )
    _create_report(
        session, company, "2025-11-01T15:00:00+09:00", PeriodType.Q2, Decimal("95"), Decimal("150"), Decimal("63.3333"), Decimal("0.95")
    )
    current = _create_report(
        session, company, "2026-02-01T15:00:00+09:00", PeriodType.Q3, Decimal("120"), Decimal("150"), None, Decimal("0.95")
    )
    guidance = GuidanceRevision(
        disclosure_id=current.disclosure_id,
        revised_operating_income_before=Decimal("145"),
        revised_operating_income_after=Decimal("150"),
        revision_rate_operating_income=Decimal("3.4483"),
        revision_direction=RevisionDirection.UP,
    )
    session.add(guidance)
    session.commit()

    result = ingest_financial_comparisons(session)
    refreshed_report = session.scalar(select(FinancialReport).where(FinancialReport.id == current.id))
    analysis = session.scalar(select(AnalysisResult).where(AnalysisResult.disclosure_id == current.disclosure_id))

    assert result["processed"] == 4
    assert refreshed_report is not None
    assert refreshed_report.progress_rate_operating_income == Decimal("80.0000")
    assert analysis is not None
    assert analysis.yoy_comparison_status == ComparisonStatus.OK
    assert analysis.qoq_comparison_status == ComparisonStatus.OK
    assert analysis.average_progress_comparison_status == ComparisonStatus.OK
    assert analysis.guidance_revision_status == RevisionDetectionStatus.REVISION_DETECTED_UP
    assert analysis.guidance_revision_judgement is not None
    assert analysis.dividend_revision_status == RevisionDetectionStatus.NO_REVISION_DETECTED
    assert analysis.overall_score is not None
    assert analysis.should_notify is True
    assert "業績予想上方修正" in analysis.auto_summary


def test_financial_comparisons_capture_q1_qoq_not_applicable_and_low_confidence() -> None:
    session = _build_session()
    company = Company(code="7203", name="Toyota")
    session.add(company)
    session.flush()

    current = _create_report(
        session, company, "2026-05-01T15:00:00+09:00", PeriodType.Q1, Decimal("50"), Decimal("200"), None, Decimal("0.70")
    )
    session.commit()

    ingest_financial_comparisons(session)
    analysis = session.scalar(select(AnalysisResult).where(AnalysisResult.disclosure_id == current.disclosure_id))

    assert analysis is not None
    assert analysis.qoq_comparison_status == ComparisonStatus.NOT_COMPARABLE
    assert analysis.qoq_comparison_error_reason == ComparisonErrorReason.Q1_QOQ_NOT_APPLICABLE
    assert analysis.yoy_comparison_status == ComparisonStatus.NEEDS_REVIEW
    assert analysis.yoy_comparison_error_reason == ComparisonErrorReason.EXTRACTION_CONFIDENCE_LOW
    assert analysis.guidance_revision_status == RevisionDetectionStatus.NO_REVISION_DETECTED
    assert analysis.dividend_revision_status == RevisionDetectionStatus.NO_REVISION_DETECTED
