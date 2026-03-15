import json
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import (
    DisclosureCategory,
    DisclosurePriority,
    JobStatus,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)
from app.models.job_run import JobRun
from app.models.notification import Notification
from app.services.disclosure_view_service import list_job_statuses, list_notifications


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_list_notifications_returns_summary_and_link() -> None:
    session = _build_session()
    company = Company(code="6758", name="Sony Group")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-13T15:00:00+09:00"),
        title="Summary of Consolidated Financial Results",
        category=DisclosureCategory.EARNINGS_REPORT,
        priority=DisclosurePriority.CRITICAL,
        source_url="https://example.com/disclosure",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    session.add(
        Notification(
            disclosure_id=disclosure.id,
            notification_type=NotificationType.ANALYSIS_ALERT,
            channel=NotificationChannel.DUMMY,
            destination="test-room",
            dedupe_key="1:analysis_alert:dummy:test-room",
            body="6758 Sony Group\n開示種別: 決算短信\n進捗率80% / 業績予想上方修正",
            status=NotificationStatus.SENT,
            sent_at=datetime.now(UTC),
        )
    )
    session.commit()

    items = list_notifications(session)

    assert len(items) == 1
    assert items[0].company_code == "6758"
    assert items[0].summary == "進捗率80% / 業績予想上方修正"
    assert items[0].detail_url == f"/disclosures/{disclosure.id}"


def test_list_job_statuses_returns_latest_run_and_last_success() -> None:
    session = _build_session()
    session.add_all(
        [
            JobRun(
                job_name="fetch_disclosures",
                status=JobStatus.SUCCESS,
                started_at=datetime.fromisoformat("2026-03-13T15:00:00+09:00"),
                finished_at=datetime.fromisoformat("2026-03-13T15:01:00+09:00"),
                processed_count=3,
                result_summary_json=json.dumps({"processed": 3, "inserted": 1, "skipped": 1, "skipped_inactive": 1}),
            ),
            JobRun(
                job_name="fetch_disclosures",
                status=JobStatus.FAILED,
                started_at=datetime.fromisoformat("2026-03-13T16:00:00+09:00"),
                finished_at=datetime.fromisoformat("2026-03-13T16:01:00+09:00"),
                processed_count=0,
                result_summary_json=json.dumps({"processed": 3, "inserted": 1, "skipped": 1, "skipped_inactive": 1}),
                error_message="dummy failure",
            ),
        ]
    )
    session.commit()

    items = list_job_statuses(session)

    assert len(items) == 1
    assert items[0].job_name == "fetch_disclosures"
    assert items[0].status_label == "失敗"
    assert items[0].result_summary_label == "inserted 1 / skipped 1 / inactive 1"
    assert items[0].error_message == "dummy failure"
    assert items[0].last_success_at_label != "不明"
