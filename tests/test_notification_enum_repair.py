from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import (
    DisclosureCategory,
    DisclosurePriority,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)
from app.repositories.notification_repository import NotificationRepository
from scripts.repair_notification_enum_values import repair_notification_enum_values


def _build_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def _seed_disclosure(session):
    company = Company(code="1111", name="Test Co")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="jpx-tdnet",
        disclosed_at=datetime.fromisoformat("2026-03-18T10:00:00+09:00"),
        title="決算短信",
        category=DisclosureCategory.EARNINGS_REPORT,
        priority=DisclosurePriority.LOW,
        source_url="https://example.com/disclosure",
        is_new=False,
        is_analysis_target=False,
    )
    session.add(disclosure)
    session.flush()
    return disclosure


def test_notification_repository_persists_enum_values() -> None:
    session = _build_session()
    disclosure = _seed_disclosure(session)
    repository = NotificationRepository(session)

    repository.create_pending(
        disclosure_id=disclosure.id,
        notification_type=NotificationType.RAW_DISCLOSURE_BATCH,
        channel=NotificationChannel.DISCORD,
        destination="raw-room",
        dedupe_key="1:raw_disclosure_batch:discord:raw-room",
        body="body",
    )
    session.commit()

    row = session.execute(text("SELECT notification_type, channel, status FROM notifications")).one()
    assert row.notification_type == "raw_disclosure_batch"
    assert row.channel == "discord"
    assert row.status == "pending"


def test_repair_notification_enum_values_rewrites_legacy_uppercase_rows() -> None:
    session = _build_session()
    disclosure = _seed_disclosure(session)
    session.execute(
        text(
            "INSERT INTO notifications (disclosure_id, notification_type, channel, destination, dedupe_key, body, status, created_at, updated_at) "
            "VALUES (:disclosure_id, :notification_type, :channel, :destination, :dedupe_key, :body, :status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {
            "disclosure_id": disclosure.id,
            "notification_type": "RAW_DISCLOSURE_BATCH",
            "channel": "DISCORD",
            "destination": "raw-room",
            "dedupe_key": "legacy",
            "body": "body",
            "status": "SENT",
        },
    )
    session.commit()

    dry_run = repair_notification_enum_values(session, apply=False)
    assert dry_run["notification_type"] == 1
    assert dry_run["channel"] == 1
    assert dry_run["status"] == 1

    applied = repair_notification_enum_values(session, apply=True)
    session.commit()
    assert applied["notification_type"] == 1

    row = session.execute(text("SELECT notification_type, channel, status FROM notifications WHERE dedupe_key = 'legacy' ")).one()
    assert row.notification_type == "raw_disclosure_batch"
    assert row.channel == "discord"
    assert row.status == "sent"
