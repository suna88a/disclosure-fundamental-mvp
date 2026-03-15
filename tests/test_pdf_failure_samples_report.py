from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import (
    DisclosureCategory,
    DisclosurePriority,
    PdfParseErrorCode,
    PdfParseStatus,
)
from app.models.pdf_file import PdfFile
from app.services.failure_summary_report import (
    collect_pdf_parse_failure_samples,
    render_pdf_parse_failure_samples,
)



def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()



def _add_failed_pdf(
    session: Session,
    *,
    disclosure_id_suffix: str,
    code: str,
    name: str,
    title: str,
    error_code: PdfParseErrorCode,
    error_message: str,
) -> None:
    company = Company(code=code, name=name)
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-13T15:00:00+09:00"),
        title=title,
        normalized_title=title.lower(),
        category=DisclosureCategory.EARNINGS_REPORT,
        priority=DisclosurePriority.CRITICAL,
        source_url=f"https://example.com/disclosures/{disclosure_id_suffix}",
        source_disclosure_id=f"dummy-{disclosure_id_suffix}",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    session.add(
        PdfFile(
            disclosure_id=disclosure.id,
            source_url=f"https://example.com/pdfs/{disclosure_id_suffix}.pdf",
            file_path=f"data/pdf/{disclosure_id_suffix}.pdf",
            parse_status=PdfParseStatus.FAILED,
            parse_error_code=error_code,
            parse_error_message=error_message,
        )
    )



def test_collect_pdf_parse_failure_samples_groups_and_limits() -> None:
    session = _build_session()
    _add_failed_pdf(
        session,
        disclosure_id_suffix="1",
        code="7203",
        name="Toyota Motor Corporation",
        title="Summary of Consolidated Financial Results",
        error_code=PdfParseErrorCode.UNSUPPORTED_FORMAT,
        error_message="Unsupported format=dummy.other",
    )
    _add_failed_pdf(
        session,
        disclosure_id_suffix="2",
        code="6758",
        name="Sony Group Corporation",
        title="Summary of Consolidated Financial Results",
        error_code=PdfParseErrorCode.UNSUPPORTED_FORMAT,
        error_message="Unsupported format=dummy.other",
    )
    _add_failed_pdf(
        session,
        disclosure_id_suffix="3",
        code="9432",
        name="NTT",
        title="Summary of Consolidated Financial Results",
        error_code=PdfParseErrorCode.FORECAST_SECTION_MISSING,
        error_message="Missing company_forecast_operating_income in financial_report payload.",
    )
    session.commit()

    report = collect_pdf_parse_failure_samples(session, limit=1)

    assert report.reason_counts[PdfParseErrorCode.UNSUPPORTED_FORMAT.value] == 2
    assert report.reason_counts[PdfParseErrorCode.FORECAST_SECTION_MISSING.value] == 1
    assert len(report.samples_by_code[PdfParseErrorCode.UNSUPPORTED_FORMAT.value]) == 1
    rendered = render_pdf_parse_failure_samples(report)
    assert "unsupported_format: 2" in rendered
    assert "forecast_section_missing: 1" in rendered



def test_collect_pdf_parse_failure_samples_filters_by_code() -> None:
    session = _build_session()
    _add_failed_pdf(
        session,
        disclosure_id_suffix="10",
        code="7203",
        name="Toyota Motor Corporation",
        title="Summary of Consolidated Financial Results",
        error_code=PdfParseErrorCode.UNSUPPORTED_FORMAT,
        error_message="Unsupported format=dummy.other",
    )
    _add_failed_pdf(
        session,
        disclosure_id_suffix="11",
        code="6758",
        name="Sony Group Corporation",
        title="Summary of Consolidated Financial Results",
        error_code=PdfParseErrorCode.TIMEOUT,
        error_message="timeout while parsing",
    )
    session.commit()

    report = collect_pdf_parse_failure_samples(
        session,
        code=PdfParseErrorCode.TIMEOUT.value,
        limit=10,
    )

    assert list(report.samples_by_code.keys()) == [PdfParseErrorCode.TIMEOUT.value]
    sample = report.samples_by_code[PdfParseErrorCode.TIMEOUT.value][0]
    assert sample.company_code == "6758"
    assert sample.parse_error_code == PdfParseErrorCode.TIMEOUT.value
