from pathlib import Path
from datetime import datetime
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.fetchers.pdf_url_resolver import DummyPdfUrlResolver
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.pdf_file import PdfFile
from app.models.enums import DisclosureCategory, DisclosurePriority, PdfDownloadStatus
from app.services.pdf_downloader import PdfDownloader
from app.services.pdf_ingestion import ingest_pdfs


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _make_storage_dir() -> Path:
    path = Path("data/test_tmp") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_pdf_ingestion_downloads_and_records_file() -> None:
    storage_dir = _make_storage_dir()
    session = _build_session()
    company = Company(code="7203", name="Toyota")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-13T15:30:00+09:00"),
        title="Notice Regarding Revision of Financial Forecasts",
        normalized_title="notice regarding revision of financial forecasts",
        category=DisclosureCategory.GUIDANCE_REVISION,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/disclosures/7203-001",
        source_disclosure_id="dummy-20260313-7203-001",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.commit()

    resolver = DummyPdfUrlResolver("data/samples/pdf_links_sample.json")
    downloader = PdfDownloader(storage_dir)
    result = ingest_pdfs(session, resolver=resolver, downloader=downloader)
    pdf_file = session.scalar(select(PdfFile).where(PdfFile.disclosure_id == disclosure.id))

    assert result["downloaded"] == 1
    assert pdf_file is not None
    assert pdf_file.download_status == PdfDownloadStatus.DOWNLOADED
    assert pdf_file.file_hash is not None
    assert Path(pdf_file.file_path).exists()


def test_pdf_ingestion_marks_missing_url() -> None:
    storage_dir = _make_storage_dir()
    session = _build_session()
    company = Company(code="9432", name="NTT")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-13T16:00:00+09:00"),
        title="Notice of Dividend Forecast Revision",
        normalized_title="notice of dividend forecast revision",
        category=DisclosureCategory.DIVIDEND_REVISION,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/disclosures/9432-001",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.commit()

    resolver = DummyPdfUrlResolver("data/samples/pdf_links_sample.json")
    downloader = PdfDownloader(storage_dir)
    result = ingest_pdfs(session, resolver=resolver, downloader=downloader)
    pdf_file = session.scalar(select(PdfFile).where(PdfFile.disclosure_id == disclosure.id))

    assert result["no_url"] == 1
    assert pdf_file is not None
    assert pdf_file.download_status == PdfDownloadStatus.NO_URL
    assert pdf_file.file_path is None


def test_pdf_ingestion_skips_redownload_when_file_exists() -> None:
    storage_dir = _make_storage_dir()
    session = _build_session()
    company = Company(code="6758", name="Sony")
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
        source_url="https://example.com/disclosures/6758-001",
        source_disclosure_id="dummy-20260313-6758-001",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.commit()

    resolver = DummyPdfUrlResolver("data/samples/pdf_links_sample.json")
    downloader = PdfDownloader(storage_dir)
    first = ingest_pdfs(session, resolver=resolver, downloader=downloader)
    second = ingest_pdfs(session, resolver=resolver, downloader=downloader)

    assert first["downloaded"] == 1
    assert second["processed"] == 0
