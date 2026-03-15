from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import (
    DisclosureCategory,
    DisclosurePriority,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    RevisionDetectionStatus,
)
from app.models.financial_report import FinancialReport
from app.models.notification import Notification
from app.models.pdf_file import PdfFile
from app.models.valuation_view import ValuationView
from app.services.disclosure_view_service import (
    category_label,
    company_display_name,
    comparison_label,
    format_decimal,
    format_score,
    download_status_label,
    get_disclosure_detail,
    list_recent_disclosures,
    notification_status_label,
    parse_status_label,
    priority_label,
    revision_detection_label,
)


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_list_recent_disclosures_returns_mobile_summary() -> None:
    session = _build_session()
    company = Company(code="6758", name="Sony Group", name_ja="ソニーグループ")
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
            auto_summary="進捗率80.0000% / 業績予想上方修正 / 配当修正なし",
            should_notify=True,
            guidance_revision_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
        )
    )
    session.commit()

    items = list_recent_disclosures(session)

    assert len(items) == 1
    assert items[0].company_code == "6758"
    assert items[0].company_name == "ソニーグループ"
    assert items[0].category_label == "決算短信"
    assert items[0].summary == "進捗率80.0000% / 業績予想上方修正 / 配当修正なし"


def test_get_disclosure_detail_loads_related_objects() -> None:
    session = _build_session()
    company = Company(code="6758", name="Sony Group", name_ja="ソニーグループ")
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
    session.add(PdfFile(disclosure_id=disclosure.id, source_url="data/sample.pdf"))
    session.add(FinancialReport(disclosure_id=disclosure.id, sales=Decimal("1000"), extraction_version="v1"))
    session.add(ValuationView(disclosure_id=disclosure.id, eps_revision_view="EPS上振れ余地"))
    session.add(
        Notification(
            disclosure_id=disclosure.id,
            notification_type=NotificationType.ANALYSIS_ALERT,
            channel=NotificationChannel.DUMMY,
            destination="test-room",
            dedupe_key="1:analysis_alert:dummy:test-room",
            body="通知本文",
            status=NotificationStatus.SENT,
        )
    )
    session.commit()

    loaded = get_disclosure_detail(session, disclosure.id)

    assert loaded is not None
    assert company_display_name(loaded.company) == "ソニーグループ"
    assert len(loaded.pdf_files) == 1
    assert len(loaded.financial_reports) == 1
    assert len(loaded.valuation_views) == 1
    assert len(loaded.notifications) == 1


def test_display_label_helpers_return_japanese() -> None:
    assert category_label(DisclosureCategory.GUIDANCE_REVISION) == "業績予想の修正"
    assert priority_label(DisclosurePriority.HIGH) == "高"
    assert download_status_label(None) == "不明"
    assert parse_status_label(None) == "不明"
    assert notification_status_label(NotificationStatus.SENT) == "送信済み"
    assert format_decimal(Decimal("1234567.89")) == "1,234,568"
    assert format_decimal(Decimal("74.1935"), "%") == "74.2%"
    assert format_score(Decimal("3.04")) == "3.0"
    assert comparison_label(None, None) == "未判定"
    assert revision_detection_label(RevisionDetectionStatus.NO_REVISION_DETECTED, "guidance") == "業績予想の修正は確認されず"
