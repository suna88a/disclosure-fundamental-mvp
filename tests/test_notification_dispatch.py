from decimal import Decimal
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import Base
from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import (
    ComparisonErrorReason,
    ComparisonStatus,
    DisclosureCategory,
    DisclosurePriority,
    NotificationStatus,
    NotificationType,
    RevisionDetectionStatus,
)
from app.models.notification import Notification
from app.models.valuation_view import ValuationView
from app.services.notification_dispatch import dispatch_notifications, dispatch_raw_disclosure_notifications
from app.services.notifiers import NotificationSendResult


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_dispatch_notifications_sends_once_and_persists_log(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "test-room")
    monkeypatch.setenv("WEB_BASE_URL", "https://example.com/app")
    get_settings.cache_clear()

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
    analysis = AnalysisResult(
        disclosure_id=disclosure.id,
        auto_summary="進捗率80% / 業績予想上方修正",
        overall_score=Decimal("3.0"),
        should_notify=True,
        guidance_revision_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
        dividend_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
        yoy_comparison_status=ComparisonStatus.OK,
        yoy_comparison_error_reason=ComparisonErrorReason.NONE,
    )
    valuation = ValuationView(
        disclosure_id=disclosure.id,
        eps_revision_view="EPSの上振れ余地が意識されやすい。",
        short_term_reaction_view="短期反応はポジティブ寄りを想定。",
        valuation_comment="仮説コメント",
    )
    session.add_all([analysis, valuation])
    session.commit()

    first = dispatch_notifications(session)
    second = dispatch_notifications(session)
    notifications = list(session.scalars(select(Notification)))

    assert first["sent"] == 1
    assert second["skipped"] == 1
    assert len(notifications) == 1
    assert notifications[0].status == NotificationStatus.SENT



def test_dispatch_notifications_skips_inactive_company(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "test-room")
    monkeypatch.setenv("WEB_BASE_URL", "https://example.com/app")
    get_settings.cache_clear()

    session = _build_session()
    company = Company(code="7203", name="Toyota", is_active=False)
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
        AnalysisResult(
            disclosure_id=disclosure.id,
            auto_summary="進捗率80% / 業績予想上方修正",
            overall_score=Decimal("3.0"),
            should_notify=True,
            guidance_revision_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
            dividend_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
            yoy_comparison_status=ComparisonStatus.OK,
            yoy_comparison_error_reason=ComparisonErrorReason.NONE,
        )
    )
    session.commit()

    result = dispatch_notifications(session)

    assert result["processed"] == 0
    assert session.scalar(select(Notification)) is None



def test_dispatch_notifications_uses_discord_channel(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "discord")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "discord-room")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    monkeypatch.setenv("WEB_BASE_URL", "https://example.com/app")
    get_settings.cache_clear()

    sent_payloads: list[tuple[str, str]] = []

    def fake_send(self, destination: str, body: str) -> NotificationSendResult:
        sent_payloads.append((destination, body))
        return NotificationSendResult(external_message_id="discord-message-1")

    monkeypatch.setattr("app.services.notification_dispatch.DiscordNotifier.send", fake_send)

    session = _build_session()
    company = Company(code="9432", name="NTT", name_ja="日本電信電話")
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
    analysis = AnalysisResult(
        disclosure_id=disclosure.id,
        auto_summary="進捗率80% / 業績予想上方修正",
        overall_score=Decimal("3.0"),
        should_notify=True,
        guidance_revision_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
        dividend_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
        yoy_comparison_status=ComparisonStatus.OK,
        yoy_comparison_error_reason=ComparisonErrorReason.NONE,
    )
    valuation = ValuationView(
        disclosure_id=disclosure.id,
        eps_revision_view="EPSの上振れ余地が意識されやすい。",
        short_term_reaction_view="短期反応はポジティブ寄りを想定。",
        valuation_comment="仮説コメント",
    )
    session.add_all([analysis, valuation])
    session.commit()

    result = dispatch_notifications(session)
    notification = session.scalar(select(Notification))

    assert result["sent"] == 1
    assert sent_payloads
    assert sent_payloads[0][0] == "discord-room"
    assert notification is not None
    assert notification.status == NotificationStatus.SENT
    assert notification.channel.value == "discord"



def test_dispatch_notifications_requires_discord_webhook_url(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "discord")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "discord-room")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("WEB_BASE_URL", "https://example.com/app")
    get_settings.cache_clear()

    session = _build_session()

    try:
        dispatch_notifications(session)
    except ValueError as exc:
        assert "DISCORD_WEBHOOK_URL" in str(exc)
    else:
        raise AssertionError("Expected ValueError when DISCORD_WEBHOOK_URL is missing.")



def test_dispatch_raw_notifications_batches_and_dedupes(monkeypatch) -> None:
    monkeypatch.setenv("RAW_NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("RAW_NOTIFICATION_DESTINATION", "raw-room")
    monkeypatch.setenv("RAW_NOTIFICATION_BATCH_SIZE", "2")
    get_settings.cache_clear()

    sent_payloads: list[tuple[str, str]] = []

    def fake_send(self, destination: str, body: str) -> NotificationSendResult:
        sent_payloads.append((destination, body))
        return NotificationSendResult(external_message_id=f"dummy-raw-{len(sent_payloads)}")

    monkeypatch.setattr("app.services.notification_dispatch.DummyNotifier.send", fake_send)

    session = _build_session()
    companies = [
        Company(code="1111", name="A", is_active=False),
        Company(code="2222", name="B"),
        Company(code="3333", name="C"),
    ]
    session.add_all(companies)
    session.flush()

    disclosures = []
    for idx, company in enumerate(companies, start=1):
        disclosure = Disclosure(
            company_id=company.id,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat(f"2026-03-13T15:0{idx}:00+09:00"),
            title=f"開示タイトル{idx}",
            category=DisclosureCategory.OTHER,
            priority=DisclosurePriority.LOW,
            source_url=f"https://example.com/raw/{idx}",
            is_new=False,
            is_analysis_target=False,
        )
        disclosures.append(disclosure)
    session.add_all(disclosures)
    session.flush()
    recent = datetime.now(disclosures[0].created_at.tzinfo) - timedelta(minutes=5)
    for disclosure in disclosures:
        disclosure.created_at = recent
    session.commit()

    first = dispatch_raw_disclosure_notifications(session)
    second = dispatch_raw_disclosure_notifications(session)
    notifications = list(session.scalars(select(Notification).where(Notification.notification_type == NotificationType.RAW_DISCLOSURE_BATCH)))

    assert first["processed"] == 3
    assert first["sent"] == 3
    assert first["messages_sent"] == 2
    assert second["skipped"] == 3
    assert len(sent_payloads) == 2
    assert all(payload[0] == "raw-room" for payload in sent_payloads)
    combined_bodies = "\n".join(body for _, body in sent_payloads)
    assert "https://example.com/raw/1" in combined_bodies
    assert "https://example.com/raw/2" in combined_bodies
    assert "https://example.com/raw/3" in combined_bodies
    assert len(notifications) == 3



def test_dispatch_raw_notifications_can_backfill_one_day(monkeypatch) -> None:
    monkeypatch.setenv("RAW_NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("RAW_NOTIFICATION_DESTINATION", "raw-room")
    monkeypatch.setenv("RAW_NOTIFICATION_BATCH_SIZE", "10")
    get_settings.cache_clear()

    sent_payloads: list[str] = []

    def fake_send(self, destination: str, body: str) -> NotificationSendResult:
        sent_payloads.append(body)
        return NotificationSendResult(external_message_id=f"dummy-backfill-{len(sent_payloads)}")

    monkeypatch.setattr("app.services.notification_dispatch.DummyNotifier.send", fake_send)

    session = _build_session()
    company = Company(code="7777", name="Replay Co")
    session.add(company)
    session.flush()
    session.add_all([
        Disclosure(
            company_id=company.id,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat("2026-03-17T09:00:00+09:00"),
            title="当日開示A",
            category=DisclosureCategory.OTHER,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/replay/a",
            is_new=False,
            is_analysis_target=False,
        ),
        Disclosure(
            company_id=company.id,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat("2026-03-17T10:00:00+09:00"),
            title="当日開示B",
            category=DisclosureCategory.OTHER,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/replay/b",
            is_new=False,
            is_analysis_target=False,
        ),
        Disclosure(
            company_id=company.id,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat("2026-03-16T10:00:00+09:00"),
            title="前日開示",
            category=DisclosureCategory.OTHER,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/replay/c",
            is_new=False,
            is_analysis_target=False,
        ),
    ])
    session.commit()

    result = dispatch_raw_disclosure_notifications(session, target_date=date(2026, 3, 17))

    assert result["processed"] == 2
    assert result["sent"] == 2
    assert len(sent_payloads) == 1
    assert "https://example.com/replay/a" in sent_payloads[0]
    assert "https://example.com/replay/b" in sent_payloads[0]
    assert "https://example.com/replay/c" not in sent_payloads[0]



def test_dispatch_raw_notifications_supports_dry_run(monkeypatch) -> None:
    monkeypatch.setenv("RAW_NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("RAW_NOTIFICATION_DESTINATION", "raw-room")
    monkeypatch.setenv("RAW_NOTIFICATION_BATCH_SIZE", "10")
    monkeypatch.setenv("RAW_NOTIFICATION_LOOKBACK_MINUTES", "60")
    get_settings.cache_clear()

    session = _build_session()
    company = Company(code="5555", name="Dry Run Co")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="jpx-tdnet",
        disclosed_at=datetime.fromisoformat("2026-03-17T11:00:00+09:00"),
        title="決算短信",
        category=DisclosureCategory.EARNINGS_REPORT,
        priority=DisclosurePriority.LOW,
        source_url="https://example.com/dry-run",
        is_new=False,
        is_analysis_target=False,
    )
    session.add(disclosure)
    session.flush()
    disclosure.created_at = datetime.now(disclosure.created_at.tzinfo) - timedelta(minutes=5)
    session.commit()

    result = dispatch_raw_disclosure_notifications(session, dry_run=True)

    assert result["processed"] == 1
    assert result["dry_run"] == 1
    assert result["batch_count"] == 1
    assert session.scalar(select(Notification).where(Notification.notification_type == NotificationType.RAW_DISCLOSURE_BATCH)) is None



def test_dispatch_raw_notifications_supports_force_resend(monkeypatch) -> None:
    monkeypatch.setenv("RAW_NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("RAW_NOTIFICATION_DESTINATION", "raw-room")
    monkeypatch.setenv("RAW_NOTIFICATION_BATCH_SIZE", "10")
    monkeypatch.setenv("RAW_NOTIFICATION_LOOKBACK_MINUTES", "60")
    get_settings.cache_clear()

    sent_payloads: list[str] = []

    def fake_send(self, destination: str, body: str) -> NotificationSendResult:
        sent_payloads.append(body)
        return NotificationSendResult(external_message_id=f"dummy-force-{len(sent_payloads)}")

    monkeypatch.setattr("app.services.notification_dispatch.DummyNotifier.send", fake_send)

    session = _build_session()
    company = Company(code="6666", name="Force Co")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="jpx-tdnet",
        disclosed_at=datetime.fromisoformat("2026-03-17T12:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=DisclosureCategory.OTHER,
        priority=DisclosurePriority.LOW,
        source_url="https://example.com/force",
        is_new=False,
        is_analysis_target=False,
    )
    session.add(disclosure)
    session.flush()
    disclosure.created_at = datetime.now(disclosure.created_at.tzinfo) - timedelta(minutes=5)
    session.commit()

    first = dispatch_raw_disclosure_notifications(session)
    second = dispatch_raw_disclosure_notifications(session, target_date=date(2026, 3, 17), force=True)

    assert first["sent"] == 1
    assert second["sent"] == 1
    assert len(sent_payloads) == 2
    assert session.scalars(select(Notification).where(Notification.notification_type == NotificationType.RAW_DISCLOSURE_BATCH)).all()



def test_dispatch_raw_notifications_force_requires_date(monkeypatch) -> None:
    monkeypatch.setenv("RAW_NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("RAW_NOTIFICATION_DESTINATION", "raw-room")
    get_settings.cache_clear()

    session = _build_session()

    try:
        dispatch_raw_disclosure_notifications(session, force=True)
    except ValueError as exc:
        assert "requires --date" in str(exc)
    else:
        raise AssertionError("Expected ValueError when --force is used without --date.")



def test_dispatch_raw_notifications_requires_discord_webhook(monkeypatch) -> None:
    monkeypatch.setenv("RAW_NOTIFICATION_CHANNEL", "discord")
    monkeypatch.setenv("RAW_NOTIFICATION_DESTINATION", "discord-raw")
    monkeypatch.delenv("RAW_DISCORD_WEBHOOK_URL", raising=False)
    get_settings.cache_clear()

    session = _build_session()

    try:
        dispatch_raw_disclosure_notifications(session)
    except ValueError as exc:
        assert "DISCORD_WEBHOOK_URL" in str(exc)
    else:
        raise AssertionError("Expected ValueError when RAW_DISCORD_WEBHOOK_URL is missing.")
