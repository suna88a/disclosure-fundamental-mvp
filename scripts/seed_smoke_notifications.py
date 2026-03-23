from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.dividend_revision import DividendRevision
from app.models.guidance_revision import GuidanceRevision
from app.models.enums import (
    ComparisonErrorReason,
    ComparisonStatus,
    DisclosureCategory,
    DisclosurePriority,
    RevisionDetectionStatus,
)
from app.models.financial_report import FinancialReport
from app.models.notification import Notification
from app.models.price_daily import PriceDaily

SMOKE_CODES = ("9101", "9102", "9103", "9104")
SMOKE_SOURCE_NAME = "smoke-seed"
SMOKE_TRADE_DATE = date(2026, 3, 19)


def seed_smoke_notifications(session: Session) -> dict[str, int]:
    _delete_existing_smoke_seed(session)

    seeded_companies = [
        Company(code="9101", name="Smoke Guidance Forecast", name_ja="スモーク業績予想"),
        Company(code="9102", name="Smoke Dividend Full", name_ja="スモーク配当修正"),
        Company(code="9103", name="Smoke Guidance Actual", name_ja="スモーク実績EPS"),
        Company(code="9104", name="Smoke Dividend Partial", name_ja="スモーク部分配当"),
    ]
    session.add_all(seeded_companies)
    session.flush()
    companies = {company.code: company for company in seeded_companies}

    disclosures = [
        Disclosure(
            company_id=companies["9101"].id,
            source_name=SMOKE_SOURCE_NAME,
            disclosed_at=datetime.fromisoformat("2026-03-21T15:00:00+09:00"),
            title="業績予想の修正に関するお知らせ",
            category=DisclosureCategory.GUIDANCE_REVISION,
            priority=DisclosurePriority.HIGH,
            source_url="https://example.com/smoke/guidance-forecast",
            source_disclosure_id="smoke-guidance-forecast",
            is_new=True,
            is_analysis_target=True,
        ),
        Disclosure(
            company_id=companies["9102"].id,
            source_name=SMOKE_SOURCE_NAME,
            disclosed_at=datetime.fromisoformat("2026-03-21T15:10:00+09:00"),
            title="配当予想の修正に関するお知らせ",
            category=DisclosureCategory.DIVIDEND_REVISION,
            priority=DisclosurePriority.HIGH,
            source_url="https://example.com/smoke/dividend-full",
            source_disclosure_id="smoke-dividend-full",
            is_new=True,
            is_analysis_target=True,
        ),
        Disclosure(
            company_id=companies["9103"].id,
            source_name=SMOKE_SOURCE_NAME,
            disclosed_at=datetime.fromisoformat("2026-03-21T15:20:00+09:00"),
            title="業績予想の修正に関するお知らせ",
            category=DisclosureCategory.GUIDANCE_REVISION,
            priority=DisclosurePriority.HIGH,
            source_url="https://example.com/smoke/guidance-actual",
            source_disclosure_id="smoke-guidance-actual",
            is_new=True,
            is_analysis_target=True,
        ),
        Disclosure(
            company_id=companies["9104"].id,
            source_name=SMOKE_SOURCE_NAME,
            disclosed_at=datetime.fromisoformat("2026-03-21T15:30:00+09:00"),
            title="配当予想の修正に関するお知らせ",
            category=DisclosureCategory.DIVIDEND_REVISION,
            priority=DisclosurePriority.HIGH,
            source_url="https://example.com/smoke/dividend-partial",
            source_disclosure_id="smoke-dividend-partial",
            is_new=True,
            is_analysis_target=True,
        ),
    ]
    session.add_all(disclosures)
    session.flush()
    disclosure_by_url = {disclosure.source_url: disclosure for disclosure in disclosures}

    session.add_all([
        AnalysisResult(
            disclosure_id=disclosure_by_url["https://example.com/smoke/guidance-forecast"].id,
            auto_summary="会社予想EPSありの業績修正",
            overall_score=Decimal("3.2"),
            should_notify=True,
            guidance_revision_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
            dividend_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
            yoy_comparison_status=ComparisonStatus.OK,
            yoy_comparison_error_reason=ComparisonErrorReason.NONE,
        ),
        AnalysisResult(
            disclosure_id=disclosure_by_url["https://example.com/smoke/dividend-full"].id,
            auto_summary="年間配当ありの配当修正",
            overall_score=Decimal("2.8"),
            should_notify=True,
            guidance_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
            dividend_revision_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
            yoy_comparison_status=ComparisonStatus.OK,
            yoy_comparison_error_reason=ComparisonErrorReason.NONE,
        ),
        AnalysisResult(
            disclosure_id=disclosure_by_url["https://example.com/smoke/guidance-actual"].id,
            auto_summary="実績EPS fallback の業績修正",
            overall_score=Decimal("2.1"),
            should_notify=True,
            guidance_revision_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
            dividend_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
            yoy_comparison_status=ComparisonStatus.OK,
            yoy_comparison_error_reason=ComparisonErrorReason.NONE,
        ),
        AnalysisResult(
            disclosure_id=disclosure_by_url["https://example.com/smoke/dividend-partial"].id,
            auto_summary="partial DPS の配当修正",
            overall_score=Decimal("2.0"),
            should_notify=True,
            guidance_revision_status=RevisionDetectionStatus.NO_REVISION_DETECTED,
            dividend_revision_status=RevisionDetectionStatus.REVISION_DETECTED_UP,
            yoy_comparison_status=ComparisonStatus.OK,
            yoy_comparison_error_reason=ComparisonErrorReason.NONE,
        ),
    ])

    session.add_all([
        FinancialReport(
            disclosure_id=disclosure_by_url["https://example.com/smoke/guidance-forecast"].id,
            company_forecast_eps=Decimal("120.0"),
        ),
        FinancialReport(
            disclosure_id=disclosure_by_url["https://example.com/smoke/guidance-actual"].id,
            eps=Decimal("80.0"),
        ),
    ])

    session.add_all([
        GuidanceRevision(
            disclosure_id=disclosure_by_url["https://example.com/smoke/guidance-forecast"].id,
            revised_sales_before=Decimal("10000"),
            revised_sales_after=Decimal("10800"),
            revised_operating_income_before=Decimal("900"),
            revised_operating_income_after=Decimal("1100"),
            revised_ordinary_income_before=Decimal("850"),
            revised_ordinary_income_after=Decimal("1020"),
            revised_net_income_before=Decimal("600"),
            revised_net_income_after=Decimal("720"),
            revised_eps_before=Decimal("100.0"),
            revised_eps_after=Decimal("120.0"),
        ),
        GuidanceRevision(
            disclosure_id=disclosure_by_url["https://example.com/smoke/guidance-actual"].id,
            revised_operating_income_after=Decimal("950"),
            revised_eps_after=Decimal("80.0"),
        ),
    ])

    session.add_all([
        DividendRevision(
            disclosure_id=disclosure_by_url["https://example.com/smoke/dividend-full"].id,
            interim_dividend_before=Decimal("20.0"),
            interim_dividend_after=Decimal("25.0"),
            year_end_dividend_before=Decimal("30.0"),
            year_end_dividend_after=Decimal("35.0"),
            annual_dividend_before=Decimal("50.0"),
            annual_dividend_after=Decimal("60.0"),
        ),
        DividendRevision(
            disclosure_id=disclosure_by_url["https://example.com/smoke/dividend-partial"].id,
            year_end_dividend_before=Decimal("30.0"),
            year_end_dividend_after=Decimal("35.0"),
        ),
    ])

    session.add_all([
        PriceDaily(code="9101", trade_date=SMOKE_TRADE_DATE, close=Decimal("2400"), source="smoke", source_symbol="9101.T"),
        PriceDaily(code="9102", trade_date=SMOKE_TRADE_DATE, close=Decimal("3000"), source="smoke", source_symbol="9102.T"),
        PriceDaily(code="9103", trade_date=SMOKE_TRADE_DATE, close=Decimal("2400"), source="smoke", source_symbol="9103.T"),
        PriceDaily(code="9104", trade_date=SMOKE_TRADE_DATE, close=Decimal("3000"), source="smoke", source_symbol="9104.T"),
    ])

    session.commit()
    return {
        "companies": len(seeded_companies),
        "disclosures": len(disclosures),
        "analysis_results": 4,
        "financial_reports": 2,
        "guidance_revisions": 2,
        "dividend_revisions": 2,
        "price_daily": 4,
    }


def _delete_existing_smoke_seed(session: Session) -> None:
    disclosure_ids = list(
        session.scalars(
            select(Disclosure.id).where(Disclosure.source_name == SMOKE_SOURCE_NAME)
        )
    )
    if disclosure_ids:
        session.execute(delete(Notification).where(Notification.disclosure_id.in_(disclosure_ids)))
        session.execute(delete(AnalysisResult).where(AnalysisResult.disclosure_id.in_(disclosure_ids)))
        session.execute(delete(FinancialReport).where(FinancialReport.disclosure_id.in_(disclosure_ids)))
        session.execute(delete(GuidanceRevision).where(GuidanceRevision.disclosure_id.in_(disclosure_ids)))
        session.execute(delete(DividendRevision).where(DividendRevision.disclosure_id.in_(disclosure_ids)))
        session.execute(delete(Disclosure).where(Disclosure.id.in_(disclosure_ids)))

    session.execute(delete(PriceDaily).where(PriceDaily.code.in_(SMOKE_CODES)))
    session.execute(delete(Company).where(Company.code.in_(SMOKE_CODES)))
    session.flush()


def main() -> None:
    session = SessionLocal()
    try:
        result = seed_smoke_notifications(session)
        print(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()
