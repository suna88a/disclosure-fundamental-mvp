from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.fetchers.revision_extractor import DummyRevisionExtractor
from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.dividend_revision import DividendRevision
from app.models.enums import DisclosureCategory, DisclosurePriority, ToneJudgement
from app.models.guidance_revision import GuidanceRevision
from app.services.revision_ingestion import ingest_revisions


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_guidance_revision_is_saved_and_analysis_created() -> None:
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

    result = ingest_revisions(session, DummyRevisionExtractor("data/samples/revision_extractions_sample.json"))
    guidance = session.scalar(select(GuidanceRevision).where(GuidanceRevision.disclosure_id == disclosure.id))
    analysis = session.scalar(select(AnalysisResult).where(AnalysisResult.disclosure_id == disclosure.id))

    assert result["guidance_saved"] == 1
    assert guidance is not None
    assert guidance.revised_operating_income_after == Decimal("4700000")
    assert analysis is not None
    assert analysis.guidance_revision_judgement is not None
    assert analysis.comment_tone == ToneJudgement.POSITIVE
    assert analysis.should_notify is True


def test_dividend_revision_is_saved_and_analysis_created() -> None:
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

    result = ingest_revisions(session, DummyRevisionExtractor("data/samples/revision_extractions_sample.json"))
    dividend = session.scalar(select(DividendRevision).where(DividendRevision.disclosure_id == disclosure.id))
    analysis = session.scalar(select(AnalysisResult).where(AnalysisResult.disclosure_id == disclosure.id))

    assert result["dividend_saved"] == 1
    assert dividend is not None
    assert dividend.annual_dividend_after == Decimal("130")
    assert analysis is not None
    assert analysis.dividend_revision_judgement is not None
    assert analysis.should_notify is True


def test_revision_ingestion_is_idempotent_for_existing_records() -> None:
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

    extractor = DummyRevisionExtractor("data/samples/revision_extractions_sample.json")
    first = ingest_revisions(session, extractor)
    second = ingest_revisions(session, extractor)

    guidance_count = len(list(session.scalars(select(GuidanceRevision))))
    analysis_count = len(list(session.scalars(select(AnalysisResult))))

    assert first["guidance_saved"] == 1
    assert second["guidance_saved"] == 1
    assert guidance_count == 1
    assert analysis_count == 1
