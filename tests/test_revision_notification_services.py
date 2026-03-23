from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.dividend_revision import DividendRevision
from app.models.enums import DisclosureCategory, DisclosurePriority
from app.models.financial_report import FinancialReport
from app.models.guidance_revision import GuidanceRevision
from app.models.price_daily import PriceDaily
from app.services.dividend_revision_notification_service import build_dividend_revision_notification_text
from app.services.guidance_revision_notification_service import build_guidance_revision_notification_text


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_build_guidance_revision_notification_text_with_before_after_and_per() -> None:
    session = _build_session()
    company = Company(code="7203", name="Toyota", name_ja="トヨタ自動車")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-21T15:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=DisclosureCategory.GUIDANCE_REVISION,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/guidance",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    session.add(GuidanceRevision(
        disclosure_id=disclosure.id,
        revised_sales_before=Decimal("10000"),
        revised_sales_after=Decimal("10800"),
        revised_operating_income_before=Decimal("900"),
        revised_operating_income_after=Decimal("1100"),
        revised_eps_before=Decimal("100.0"),
        revised_eps_after=Decimal("120.0"),
    ))
    session.add(FinancialReport(disclosure_id=disclosure.id, company_forecast_eps=Decimal("120.0")))
    session.add(PriceDaily(code="7203", trade_date=date(2026, 3, 19), close=Decimal("2400"), source="smoke", source_symbol="7203.T"))
    session.commit()

    text = build_guidance_revision_notification_text(session, disclosure)
    body = "\n".join(text.body_lines)

    assert text.headline == "[業績修正] 7203 トヨタ自動車"
    assert "売上高: 10,000 -> 10,800" in body
    assert "営業利益: 900 -> 1,100" in body
    assert "EPS: 100.0 -> 120.0" in body
    assert "PER(会社予想EPS): 20.0" in body


def test_build_guidance_revision_notification_text_survives_missing_values_and_actual_eps_fallback() -> None:
    session = _build_session()
    company = Company(code="7204", name="Actual EPS", name_ja="実績EPS")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-21T15:00:00+09:00"),
        title="業績予想の修正に関するお知らせ",
        category=DisclosureCategory.GUIDANCE_REVISION,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/guidance-actual",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    session.add(GuidanceRevision(
        disclosure_id=disclosure.id,
        revised_operating_income_after=Decimal("950"),
        revised_eps_after=Decimal("80.0"),
    ))
    session.add(FinancialReport(disclosure_id=disclosure.id, eps=Decimal("80.0")))
    session.add(PriceDaily(code="7204", trade_date=date(2026, 3, 19), close=Decimal("2400"), source="smoke", source_symbol="7204.T"))
    session.commit()

    text = build_guidance_revision_notification_text(session, disclosure)
    body = "\n".join(text.body_lines)

    assert "営業利益: 修正後 950" in body
    assert "EPS: 修正後 80.0" in body
    assert "PER(会社予想EPS):" not in body


def test_build_dividend_revision_notification_text_with_before_after_and_yield() -> None:
    session = _build_session()
    company = Company(code="9432", name="NTT", name_ja="日本電信電話")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-21T15:10:00+09:00"),
        title="配当予想の修正に関するお知らせ",
        category=DisclosureCategory.DIVIDEND_REVISION,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/dividend",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    session.add(DividendRevision(
        disclosure_id=disclosure.id,
        interim_dividend_before=Decimal("20.0"),
        interim_dividend_after=Decimal("25.0"),
        year_end_dividend_before=Decimal("30.0"),
        year_end_dividend_after=Decimal("35.0"),
        annual_dividend_before=Decimal("50.0"),
        annual_dividend_after=Decimal("60.0"),
    ))
    session.add(PriceDaily(code="9432", trade_date=date(2026, 3, 19), close=Decimal("3000"), source="smoke", source_symbol="9432.T"))
    session.commit()

    text = build_dividend_revision_notification_text(session, disclosure)
    body = "\n".join(text.body_lines)

    assert text.headline == "[配当修正] 9432 日本電信電話"
    assert "中間配当: 20.0 -> 25.0" in body
    assert "期末配当: 30.0 -> 35.0" in body
    assert "年間配当: 50.0 -> 60.0" in body
    assert "配当利回り: 2.0%" in body


def test_build_dividend_revision_notification_text_suppresses_yield_for_partial_dps() -> None:
    session = _build_session()
    company = Company(code="9433", name="Partial DPS", name_ja="部分配当")
    session.add(company)
    session.flush()
    disclosure = Disclosure(
        company_id=company.id,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-21T15:10:00+09:00"),
        title="配当予想の修正に関するお知らせ",
        category=DisclosureCategory.DIVIDEND_REVISION,
        priority=DisclosurePriority.HIGH,
        source_url="https://example.com/dividend-partial",
        is_new=True,
        is_analysis_target=True,
    )
    session.add(disclosure)
    session.flush()
    session.add(DividendRevision(
        disclosure_id=disclosure.id,
        year_end_dividend_before=Decimal("30.0"),
        year_end_dividend_after=Decimal("35.0"),
    ))
    session.add(PriceDaily(code="9433", trade_date=date(2026, 3, 19), close=Decimal("3000"), source="smoke", source_symbol="9433.T"))
    session.commit()

    text = build_dividend_revision_notification_text(session, disclosure)
    body = "\n".join(text.body_lines)

    assert "期末配当: 30.0 -> 35.0" in body
    assert "配当利回り:" not in body
