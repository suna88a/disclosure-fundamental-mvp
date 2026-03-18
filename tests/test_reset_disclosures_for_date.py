from datetime import date, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.dividend_revision import DividendRevision
from app.models.enums import DisclosureCategory, DisclosurePriority, NotificationChannel, NotificationStatus, NotificationType
from app.models.notification import Notification
from app.models.pdf_file import PdfFile
from scripts.reset_disclosures_for_date import reset_disclosures_for_date


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()



def test_reset_disclosures_for_date_counts_without_deleting() -> None:
    session = _build_session()
    company = Company(code="1111", name="Reset Co")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="jpx-tdnet",
        disclosed_at=datetime.fromisoformat("2026-03-18T10:00:00+09:00"),
        title="配当予想の修正に関するお知らせ",
        category=DisclosureCategory.OTHER,
        priority=DisclosurePriority.LOW,
        source_url="https://example.com/reset",
        is_new=False,
        is_analysis_target=False,
    )
    session.add(disclosure)
    session.flush()
    session.add(Notification(
        disclosure_id=disclosure.id,
        notification_type=NotificationType.RAW_DISCLOSURE_BATCH,
        channel=NotificationChannel.DUMMY,
        destination="raw-room",
        dedupe_key="1:raw_disclosure_batch:dummy:raw-room",
        body="body",
        status=NotificationStatus.SENT,
    ))
    session.add(PdfFile(disclosure_id=disclosure.id, source_url="https://example.com/reset.pdf"))
    session.add(DividendRevision(disclosure_id=disclosure.id))
    session.commit()

    result = reset_disclosures_for_date(session, date(2026, 3, 18), apply=False)

    assert result["disclosures"] == 1
    assert result["notifications"] == 1
    assert result["pdf_files"] == 1
    assert result["dividend_revisions"] == 1
    assert session.scalar(select(Disclosure.id)) == disclosure.id



def test_reset_disclosures_for_date_deletes_related_rows() -> None:
    session = _build_session()
    company = Company(code="2222", name="Delete Co")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="jpx-tdnet",
        disclosed_at=datetime.fromisoformat("2026-03-18T11:00:00+09:00"),
        title="決算短信",
        category=DisclosureCategory.EARNINGS_REPORT,
        priority=DisclosurePriority.LOW,
        source_url="https://example.com/delete",
        is_new=False,
        is_analysis_target=False,
    )
    session.add(disclosure)
    session.flush()
    session.add(Notification(
        disclosure_id=disclosure.id,
        notification_type=NotificationType.RAW_DISCLOSURE_BATCH,
        channel=NotificationChannel.DUMMY,
        destination="raw-room",
        dedupe_key="2:raw_disclosure_batch:dummy:raw-room",
        body="body",
        status=NotificationStatus.SENT,
    ))
    session.commit()

    result = reset_disclosures_for_date(session, date(2026, 3, 18), apply=True)
    session.commit()

    assert result["disclosures"] == 1
    assert session.scalars(select(Disclosure)).all() == []
    assert session.scalars(select(Notification)).all() == []
