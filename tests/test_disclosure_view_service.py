from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.dividend_revision import DividendRevision
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
from app.models.price_daily import PriceDaily
from app.models.valuation_view import ValuationView
from app.services.disclosure_view_service import (
    category_label,
    company_display_name,
    comparison_label,
    format_decimal,
    format_score,
    download_status_label,
    get_disclosure_detail,
    get_disclosure_reference_price,
    get_disclosure_valuation_snapshot,
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


def test_get_disclosure_reference_price_returns_previous_trade_day() -> None:
    session = _build_session()
    company = Company(code="7203", name="Toyota")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-19T15:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=DisclosureCategory.OTHER,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/disclosure",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    session.add_all([
        PriceDaily(
            code="7203",
            trade_date=date(2026, 3, 18),
            open=Decimal("1000"),
            high=Decimal("1010"),
            low=Decimal("995"),
            close=Decimal("1005"),
            adj_close=Decimal("1005"),
            volume=100,
            source="yfinance",
            source_symbol="7203.T",
        ),
        PriceDaily(
            code="7203",
            trade_date=date(2026, 3, 19),
            open=Decimal("1010"),
            high=Decimal("1020"),
            low=Decimal("1008"),
            close=Decimal("1015"),
            adj_close=Decimal("1015"),
            volume=100,
            source="yfinance",
            source_symbol="7203.T",
        ),
    ])
    session.commit()

    reference_price = get_disclosure_reference_price(session, disclosure)

    assert reference_price is not None
    assert reference_price.reference_trade_date == date(2026, 3, 18)
    assert reference_price.close == Decimal("1005")
    assert reference_price.source == "yfinance"
    assert reference_price.source_symbol == "7203.T"


def test_get_disclosure_reference_price_returns_none_when_missing() -> None:
    session = _build_session()
    company = Company(code="7203", name="Toyota")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-19T15:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=DisclosureCategory.OTHER,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/disclosure",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.commit()

    reference_price = get_disclosure_reference_price(session, disclosure)

    assert reference_price is None


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


def test_get_disclosure_valuation_snapshot_returns_metrics() -> None:
    session = _build_session()
    company = Company(code="7203", name="Toyota")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-19T15:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=DisclosureCategory.OTHER,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/disclosure",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    session.add(FinancialReport(disclosure_id=disclosure.id, company_forecast_eps=Decimal("100"), extraction_version="v1"))
    session.add(
        PriceDaily(
            code="7203",
            trade_date=date(2026, 3, 18),
            open=Decimal("1000"),
            high=Decimal("1010"),
            low=Decimal("995"),
            close=Decimal("1005"),
            adj_close=Decimal("1005"),
            volume=100,
            source="yfinance",
            source_symbol="7203.T",
        )
    )
    session.add(DividendRevision(disclosure_id=disclosure.id, annual_dividend_after=Decimal("40")))
    session.commit()

    snapshot = get_disclosure_valuation_snapshot(session, disclosure)

    assert snapshot is not None
    assert snapshot.metrics.forward_per == Decimal("10.05")
    assert snapshot.metrics.dividend_yield == Decimal("0.03980099502487562189054726368")
    assert snapshot.inputs.eps_source == "company_forecast_eps"
    assert snapshot.inputs.eps_basis == "forecast"
    assert snapshot.inputs.annual_dps_source == "annual_dividend_after"
    assert snapshot.metrics.eps_basis == "forecast"
    assert snapshot.metrics.warnings == ()


def test_get_disclosure_valuation_snapshot_handles_missing_eps() -> None:
    session = _build_session()
    company = Company(code="7203", name="Toyota")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-19T15:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=DisclosureCategory.OTHER,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/disclosure",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    session.add(
        PriceDaily(
            code="7203",
            trade_date=date(2026, 3, 18),
            open=Decimal("1000"),
            high=Decimal("1010"),
            low=Decimal("995"),
            close=Decimal("1005"),
            adj_close=Decimal("1005"),
            volume=100,
            source="yfinance",
            source_symbol="7203.T",
        )
    )
    session.commit()

    snapshot = get_disclosure_valuation_snapshot(session, disclosure)

    assert snapshot is not None
    assert snapshot.metrics.forward_per is None
    assert snapshot.inputs.eps_source is None
    assert snapshot.inputs.eps_basis == "unknown"
    assert "eps_missing" in snapshot.metrics.warnings


def test_get_disclosure_valuation_snapshot_handles_missing_annual_dps() -> None:
    session = _build_session()
    company = Company(code="7203", name="Toyota")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-19T15:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=DisclosureCategory.OTHER,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/disclosure",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    session.add(FinancialReport(disclosure_id=disclosure.id, eps=Decimal("80.5"), extraction_version="v1"))
    session.add(
        PriceDaily(
            code="7203",
            trade_date=date(2026, 3, 18),
            open=Decimal("1000"),
            high=Decimal("1010"),
            low=Decimal("995"),
            close=Decimal("1005"),
            adj_close=Decimal("1005"),
            volume=100,
            source="yfinance",
            source_symbol="7203.T",
        )
    )
    session.commit()

    snapshot = get_disclosure_valuation_snapshot(session, disclosure)

    assert snapshot is not None
    assert snapshot.metrics.dividend_yield is None
    assert snapshot.inputs.annual_dps_source == "missing"
    assert "annual_dps_missing" in snapshot.metrics.warnings


def test_get_disclosure_valuation_snapshot_includes_warnings() -> None:
    session = _build_session()
    company = Company(code="7203", name="Toyota")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-19T15:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=DisclosureCategory.OTHER,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/disclosure",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.commit()

    snapshot = get_disclosure_valuation_snapshot(session, disclosure)

    assert snapshot is not None
    assert snapshot.metrics.forward_per is None
    assert snapshot.metrics.dividend_yield is None
    assert snapshot.metrics.warnings == ("reference_price_missing", "eps_missing", "annual_dps_missing")
