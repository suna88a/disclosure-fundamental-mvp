from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.fetchers.disclosure_fetcher import DisclosureRecord
from app.fetchers.pdf_url_resolver import DummyPdfUrlResolver
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory, DisclosurePriority
from app.services.disclosure_ingestion import ingest_disclosures
from app.services.pdf_downloader import PdfDownloader
from app.services.pdf_ingestion import ingest_pdfs


class StaticDisclosureFetcher:
    def __init__(self, records: list[DisclosureRecord]) -> None:
        self._records = records

    def fetch(self) -> list[DisclosureRecord]:
        return self._records



def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()



def _make_storage_dir() -> Path:
    path = Path("data/test_tmp") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path



def test_disclosure_ingestion_persists_unknown_and_inactive_companies() -> None:
    session = _build_session()
    session.add_all(
        [
            Company(code="7203", name="Toyota", is_active=True),
            Company(code="6758", name="Sony", is_active=False),
        ]
    )
    session.commit()

    fetcher = StaticDisclosureFetcher(
        [
            DisclosureRecord(
                company_code="7203",
                company_name="Toyota Motor Corporation",
                source_name="dummy",
                disclosed_at=datetime.fromisoformat("2026-03-13T15:00:00+09:00"),
                title="Summary of Consolidated Financial Results",
                source_url="https://example.com/1",
                source_disclosure_id="a1",
            ),
            DisclosureRecord(
                company_code="6758",
                company_name="Sony Group Corporation",
                source_name="dummy",
                disclosed_at=datetime.fromisoformat("2026-03-13T15:01:00+09:00"),
                title="Summary of Consolidated Financial Results",
                source_url="https://example.com/2",
                source_disclosure_id="a2",
            ),
            DisclosureRecord(
                company_code="9984",
                company_name="SoftBank Group Corp.",
                source_name="dummy",
                disclosed_at=datetime.fromisoformat("2026-03-13T15:02:00+09:00"),
                title="Notice Regarding Revision of Financial Forecasts",
                source_url="https://example.com/3",
                source_disclosure_id="a3",
            ),
        ]
    )

    result = ingest_disclosures(session, fetcher)
    saved_disclosures = list(session.scalars(select(Disclosure).order_by(Disclosure.id)))
    stub_company = session.scalar(select(Company).where(Company.code == "9984"))

    assert result["fetched"] == 3
    assert result["inserted"] == 3
    assert result["skipped_inactive"] == 0
    assert result["autocreated_companies"] == 1
    assert len(saved_disclosures) == 3
    assert stub_company is not None
    assert stub_company.is_active is False
    assert stub_company.name == "SoftBank Group Corp."



def test_pdf_ingestion_ignores_inactive_company_disclosures() -> None:
    storage_dir = _make_storage_dir()
    session = _build_session()
    company = Company(code="7203", name="Toyota", is_active=False)
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

    assert result["processed"] == 0
