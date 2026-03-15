from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.fetchers.financial_report_parser import DummyFinancialReportParser
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import (
    CumulativeType,
    DisclosureCategory,
    DisclosurePriority,
    PdfDownloadStatus,
    PdfParseErrorCode,
    PdfParseStatus,
    PeriodType,
    StatementScope,
)
from app.models.financial_report import FinancialReport
from app.models.pdf_file import PdfFile
from app.services.financial_report_ingestion import ingest_financial_reports



def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()



def _create_disclosure(session: Session, *, code: str, name: str, disclosure_id: str) -> tuple[Disclosure, PdfFile]:
    company = Company(code=code, name=name)
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-13T15:00:00+09:00"),
        title="Summary of Consolidated Financial Results for the Third Quarter",
        normalized_title="summary of consolidated financial results for the third quarter",
        category=DisclosureCategory.EARNINGS_REPORT,
        priority=DisclosurePriority.CRITICAL,
        source_url=f"https://example.com/disclosures/{disclosure_id}",
        source_disclosure_id=disclosure_id,
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    pdf_file = PdfFile(
        disclosure_id=disclosure.id,
        source_url="data/samples/pdfs/earnings_report_sample.pdf",
        file_path="data/samples/pdfs/earnings_report_sample.pdf",
        file_hash="dummyhash",
        download_status=PdfDownloadStatus.DOWNLOADED,
        downloaded_at=datetime.now(UTC),
        parse_status=PdfParseStatus.PENDING,
    )
    session.add(pdf_file)
    session.commit()
    return disclosure, pdf_file



def test_financial_report_extraction_saves_main_values_and_forecasts() -> None:
    session = _build_session()
    disclosure, pdf_file = _create_disclosure(session, code="6758", name="Sony", disclosure_id="dummy-20260313-6758-001")

    result = ingest_financial_reports(session, DummyFinancialReportParser("data/samples/financial_reports_sample.json"))

    report = session.scalar(select(FinancialReport).where(FinancialReport.disclosure_id == disclosure.id))
    refreshed_pdf = session.scalar(select(PdfFile).where(PdfFile.id == pdf_file.id))

    assert result["extracted"] == 1
    assert report is not None
    assert report.period_type == PeriodType.Q3
    assert report.statement_scope == StatementScope.CONSOLIDATED
    assert report.cumulative_type == CumulativeType.CUMULATIVE
    assert report.sales == Decimal("9800000")
    assert report.operating_income == Decimal("1150000")
    assert report.company_forecast_operating_income == Decimal("1550000")
    assert report.company_forecast_eps == Decimal("204.8")
    assert refreshed_pdf is not None
    assert refreshed_pdf.parse_status == PdfParseStatus.COMPLETED
    assert refreshed_pdf.parse_error_code is None



def test_financial_report_extraction_supports_v2_nested_summary_format() -> None:
    session = _build_session()
    disclosure, pdf_file = _create_disclosure(session, code="7203", name="Toyota", disclosure_id="dummy-20260314-7203-001")

    result = ingest_financial_reports(session, DummyFinancialReportParser("data/samples/financial_reports_sample.json"))

    report = session.scalar(select(FinancialReport).where(FinancialReport.disclosure_id == disclosure.id))
    refreshed_pdf = session.scalar(select(PdfFile).where(PdfFile.id == pdf_file.id))

    assert result["extracted"] == 1
    assert report is not None
    assert report.period_type == PeriodType.FY
    assert report.statement_scope == StatementScope.CONSOLIDATED
    assert report.cumulative_type == CumulativeType.CUMULATIVE
    assert report.sales == Decimal("45120000")
    assert report.operating_income == Decimal("5120000")
    assert report.company_forecast_operating_income == Decimal("5400000")
    assert report.company_forecast_eps == Decimal("295.1")
    assert refreshed_pdf is not None
    assert refreshed_pdf.parse_status == PdfParseStatus.COMPLETED
    assert refreshed_pdf.parse_error_code is None



def test_financial_report_extraction_supports_v3_header_and_alias_keys_format() -> None:
    session = _build_session()
    disclosure, pdf_file = _create_disclosure(session, code="8306", name="MUFG", disclosure_id="dummy-20260315-8306-001")

    result = ingest_financial_reports(session, DummyFinancialReportParser("data/samples/financial_reports_sample.json"))

    report = session.scalar(select(FinancialReport).where(FinancialReport.disclosure_id == disclosure.id))
    refreshed_pdf = session.scalar(select(PdfFile).where(PdfFile.id == pdf_file.id))

    assert result["extracted"] == 1
    assert report is not None
    assert report.period_type == PeriodType.Q2
    assert report.statement_scope == StatementScope.CONSOLIDATED
    assert report.cumulative_type == CumulativeType.CUMULATIVE
    assert report.sales == Decimal("32450000")
    assert report.operating_income == Decimal("6840000")
    assert report.ordinary_income == Decimal("7010000")
    assert report.net_income == Decimal("4890000")
    assert report.company_forecast_operating_income == Decimal("13200000")
    assert report.company_forecast_eps == Decimal("279.3")
    assert refreshed_pdf is not None
    assert refreshed_pdf.parse_status == PdfParseStatus.COMPLETED
    assert refreshed_pdf.parse_error_code is None



def test_financial_report_extraction_supports_v4_meta_results_outlook_format() -> None:
    session = _build_session()
    disclosure, pdf_file = _create_disclosure(session, code="8411", name="Mizuho", disclosure_id="dummy-20260315-8411-001")

    result = ingest_financial_reports(session, DummyFinancialReportParser("data/samples/financial_reports_sample.json"))

    report = session.scalar(select(FinancialReport).where(FinancialReport.disclosure_id == disclosure.id))
    refreshed_pdf = session.scalar(select(PdfFile).where(PdfFile.id == pdf_file.id))

    assert result["extracted"] == 1
    assert report is not None
    assert report.period_type == PeriodType.Q1
    assert report.statement_scope == StatementScope.CONSOLIDATED
    assert report.cumulative_type == CumulativeType.QUARTERLY_ONLY
    assert report.sales == Decimal("1885000")
    assert report.operating_income == Decimal("214000")
    assert report.ordinary_income == Decimal("228000")
    assert report.net_income == Decimal("157000")
    assert report.company_forecast_operating_income == Decimal("910000")
    assert report.company_forecast_eps == Decimal("199.4")
    assert refreshed_pdf is not None
    assert refreshed_pdf.parse_status == PdfParseStatus.COMPLETED
    assert refreshed_pdf.parse_error_code is None



def test_financial_report_extraction_marks_unsupported_pdf() -> None:
    session = _build_session()
    disclosure, pdf_file = _create_disclosure(session, code="6758", name="Sony", disclosure_id="dummy-unsupported-001")

    result = ingest_financial_reports(session, DummyFinancialReportParser("data/samples/financial_reports_sample.json"))
    refreshed_pdf = session.scalar(select(PdfFile).where(PdfFile.id == pdf_file.id))
    report = session.scalar(select(FinancialReport).where(FinancialReport.disclosure_id == disclosure.id))

    assert result["unsupported"] == 1
    assert report is None
    assert refreshed_pdf is not None
    assert refreshed_pdf.parse_status == PdfParseStatus.FAILED
    assert refreshed_pdf.parse_error_code == PdfParseErrorCode.MANIFEST_ENTRY_MISSING
    assert refreshed_pdf.parse_error_message is not None
