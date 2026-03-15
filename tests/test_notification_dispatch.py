from decimal import Decimal
from datetime import datetime

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
    RevisionDetectionStatus,
)
from app.models.notification import Notification
from app.models.valuation_view import ValuationView
from app.services.notification_dispatch import dispatch_notifications


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
