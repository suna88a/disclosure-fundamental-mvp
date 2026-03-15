from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory, PdfParseStatus
from app.models.financial_report import FinancialReport
from app.repositories.analysis_result_repository import AnalysisResultRepository
from app.repositories.financial_report_repository import FinancialReportRepository
from app.repositories.revision_repository import RevisionRepository
from app.services.analysis_result_builder import build_analysis_result
from app.services.comparison_reference import (
    compare_progress_vs_average,
    compare_qoq_operating_income,
    compare_yoy_operating_income,
)
from app.services.progress_calculator import calculate_progress_rate_operating_income


def ingest_financial_comparisons(session: Session) -> dict[str, int]:
    statement = (
        select(FinancialReport)
        .join(FinancialReport.disclosure)
        .join(Disclosure.company)
        .options(selectinload(FinancialReport.disclosure))
        .where(
            Company.is_active.is_(True),
            Disclosure.category == DisclosureCategory.EARNINGS_REPORT,
        )
    )
    reports = list(session.scalars(statement))

    financial_repository = FinancialReportRepository(session)
    revision_repository = RevisionRepository(session)
    analysis_repository = AnalysisResultRepository(session)

    processed = 0
    updated_progress = 0
    analysis_saved = 0

    for report in reports:
        processed += 1
        progress_rate = calculate_progress_rate_operating_income(report)
        if report.progress_rate_operating_income != progress_rate:
            financial_repository.upsert(
                report.disclosure_id,
                pdf_file_id=report.pdf_file_id,
                accounting_standard=report.accounting_standard,
                period_type=report.period_type,
                statement_scope=report.statement_scope,
                cumulative_type=report.cumulative_type,
                sales=report.sales,
                operating_income=report.operating_income,
                ordinary_income=report.ordinary_income,
                net_income=report.net_income,
                eps=report.eps,
                company_forecast_sales=report.company_forecast_sales,
                company_forecast_operating_income=report.company_forecast_operating_income,
                company_forecast_ordinary_income=report.company_forecast_ordinary_income,
                company_forecast_net_income=report.company_forecast_net_income,
                company_forecast_eps=report.company_forecast_eps,
                progress_rate_operating_income=progress_rate,
                extraction_confidence=report.extraction_confidence,
                extraction_version=report.extraction_version,
            )
            report.progress_rate_operating_income = progress_rate
            updated_progress += 1

        yoy = compare_yoy_operating_income(session, report)
        qoq = compare_qoq_operating_income(session, report)
        avg_progress = compare_progress_vs_average(session, report)
        guidance_revision = revision_repository.get_guidance_revision(report.disclosure_id)
        dividend_revision = revision_repository.get_dividend_revision(report.disclosure_id)
        built = build_analysis_result(
            report=report,
            yoy=yoy,
            qoq=qoq,
            avg_progress=avg_progress,
            guidance_revision=guidance_revision,
            dividend_revision=dividend_revision,
        )

        analysis_repository.upsert(
            report.disclosure_id,
            progress_judgement=built.progress_judgement,
            guidance_revision_status=built.guidance_revision_status,
            guidance_revision_judgement=built.guidance_revision_judgement,
            dividend_revision_status=built.dividend_revision_status,
            dividend_revision_judgement=built.dividend_revision_judgement,
            comment_tone=built.tone_judgement,
            auto_summary=built.short_summary,
            overall_score=built.overall_score,
            total_score=built.overall_score,
            should_notify=built.should_notify,
            yoy_comparison_status=yoy.status,
            yoy_comparison_error_reason=yoy.error_reason,
            qoq_comparison_status=qoq.status,
            qoq_comparison_error_reason=qoq.error_reason,
            average_progress_comparison_status=avg_progress.status,
            average_progress_comparison_error_reason=avg_progress.error_reason,
        )
        analysis_saved += 1

    session.flush()
    session.expire_all()
    return {
        "processed": processed,
        "updated_progress": updated_progress,
        "analysis_saved": analysis_saved,
    }
