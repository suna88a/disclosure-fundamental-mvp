from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.disclosure import Disclosure
from app.models.enums import ComparisonErrorReason, ComparisonStatus, PeriodType
from app.models.financial_report import FinancialReport


CONFIDENCE_THRESHOLD = Decimal("0.8000")


@dataclass(frozen=True)
class ComparisonOutcome:
    status: ComparisonStatus
    error_reason: ComparisonErrorReason
    value: Decimal | None
    reference_report_id: int | None
    detail: str


def get_reference_reports(session: Session, current_report: FinancialReport) -> list[FinancialReport]:
    statement = (
        select(FinancialReport)
        .join(FinancialReport.disclosure)
        .options(selectinload(FinancialReport.disclosure))
        .where(
            Disclosure.company_id == current_report.disclosure.company_id,
            Disclosure.disclosed_at < current_report.disclosure.disclosed_at,
        )
        .order_by(Disclosure.disclosed_at.desc())
    )
    return list(session.scalars(statement))


def compare_yoy_operating_income(session: Session, current_report: FinancialReport) -> ComparisonOutcome:
    return _compare_against_reference(
        session=session,
        current_report=current_report,
        reference_period=current_report.period_type,
        label="YoY operating income",
    )


def compare_qoq_operating_income(session: Session, current_report: FinancialReport) -> ComparisonOutcome:
    if current_report.period_type == PeriodType.Q1:
        return ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.Q1_QOQ_NOT_APPLICABLE,
            value=None,
            reference_report_id=None,
            detail="QoQ comparison is not applicable for 1Q.",
        )

    previous_period = {
        PeriodType.Q2: PeriodType.Q1,
        PeriodType.Q3: PeriodType.Q2,
        PeriodType.FY: PeriodType.Q3,
    }.get(current_report.period_type)

    if previous_period is None:
        return ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
            value=None,
            reference_report_id=None,
            detail="QoQ comparison period could not be determined.",
        )

    return _compare_against_reference(
        session=session,
        current_report=current_report,
        reference_period=previous_period,
        label="QoQ operating income",
    )


def compare_progress_vs_average(session: Session, current_report: FinancialReport) -> ComparisonOutcome:
    current_progress = current_report.progress_rate_operating_income
    if current_progress is None:
        return ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
            value=None,
            reference_report_id=None,
            detail="Current progress rate is unavailable.",
        )

    if _is_low_confidence(current_report):
        return ComparisonOutcome(
            status=ComparisonStatus.NEEDS_REVIEW,
            error_reason=ComparisonErrorReason.EXTRACTION_CONFIDENCE_LOW,
            value=None,
            reference_report_id=None,
            detail="Current report extraction confidence is below threshold.",
        )

    references = get_reference_reports(session, current_report)
    comparable = [
        report
        for report in references
        if report.period_type == current_report.period_type
        and report.statement_scope == current_report.statement_scope
        and report.cumulative_type == current_report.cumulative_type
        and report.accounting_standard == current_report.accounting_standard
        and report.progress_rate_operating_income is not None
        and not _is_low_confidence(report)
    ]

    if not comparable:
        return _build_mismatch_outcome(
            current_report=current_report,
            references=references,
            target_period=current_report.period_type,
            missing_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
            default_detail="No comparable history for average progress comparison.",
        )

    average_progress = sum(report.progress_rate_operating_income for report in comparable) / Decimal(
        len(comparable)
    )
    diff = (current_progress - average_progress).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return ComparisonOutcome(
        status=ComparisonStatus.OK,
        error_reason=ComparisonErrorReason.NONE,
        value=diff,
        reference_report_id=comparable[0].id,
        detail=f"Current progress rate differs from historical average by {diff} points.",
    )


def _compare_against_reference(
    session: Session,
    current_report: FinancialReport,
    reference_period: PeriodType | None,
    label: str,
) -> ComparisonOutcome:
    if reference_period is None:
        return ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
            value=None,
            reference_report_id=None,
            detail=f"{label}: reference period is unavailable.",
        )

    if _is_low_confidence(current_report):
        return ComparisonOutcome(
            status=ComparisonStatus.NEEDS_REVIEW,
            error_reason=ComparisonErrorReason.EXTRACTION_CONFIDENCE_LOW,
            value=None,
            reference_report_id=None,
            detail=f"{label}: current report extraction confidence is below threshold.",
        )

    references = get_reference_reports(session, current_report)
    exact_matches = [
        report
        for report in references
        if report.period_type == reference_period
        and report.statement_scope == current_report.statement_scope
        and report.cumulative_type == current_report.cumulative_type
        and report.accounting_standard == current_report.accounting_standard
    ]

    if not exact_matches:
        return _build_mismatch_outcome(
            current_report=current_report,
            references=references,
            target_period=reference_period,
            missing_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
            default_detail=f"{label}: no exact comparable report found.",
        )

    reference = exact_matches[0]
    if _is_low_confidence(reference):
        return ComparisonOutcome(
            status=ComparisonStatus.NEEDS_REVIEW,
            error_reason=ComparisonErrorReason.EXTRACTION_CONFIDENCE_LOW,
            value=None,
            reference_report_id=reference.id,
            detail=f"{label}: reference report extraction confidence is below threshold.",
        )

    current_value = current_report.operating_income
    reference_value = reference.operating_income
    if current_value is None or reference_value is None or reference_value == 0:
        return ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.INSUFFICIENT_HISTORY,
            value=None,
            reference_report_id=reference.id,
            detail=f"{label}: operating income values are unavailable for comparison.",
        )

    diff_pct = (((current_value - reference_value) / abs(reference_value)) * Decimal("100")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    return ComparisonOutcome(
        status=ComparisonStatus.OK,
        error_reason=ComparisonErrorReason.NONE,
        value=diff_pct,
        reference_report_id=reference.id,
        detail=f"{label}: operating income changed by {diff_pct}%.",
    )


def _build_mismatch_outcome(
    current_report: FinancialReport,
    references: list[FinancialReport],
    target_period: PeriodType | None,
    missing_reason: ComparisonErrorReason,
    default_detail: str,
) -> ComparisonOutcome:
    same_period = [report for report in references if report.period_type == target_period]
    if not same_period:
        return ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=missing_reason,
            value=None,
            reference_report_id=None,
            detail=default_detail,
        )

    same_scope = [
        report for report in same_period if report.statement_scope == current_report.statement_scope
    ]
    if not same_scope:
        return ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.SCOPE_MISMATCH,
            value=None,
            reference_report_id=same_period[0].id,
            detail="Comparable period exists, but statement scope differs.",
        )

    same_cumulative = [
        report for report in same_scope if report.cumulative_type == current_report.cumulative_type
    ]
    if not same_cumulative:
        return ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.CUMULATIVE_MISMATCH,
            value=None,
            reference_report_id=same_scope[0].id,
            detail="Comparable period exists, but cumulative type differs.",
        )

    same_accounting = [
        report
        for report in same_cumulative
        if report.accounting_standard == current_report.accounting_standard
    ]
    if not same_accounting:
        return ComparisonOutcome(
            status=ComparisonStatus.NOT_COMPARABLE,
            error_reason=ComparisonErrorReason.ACCOUNTING_STANDARD_MISMATCH,
            value=None,
            reference_report_id=same_cumulative[0].id,
            detail="Comparable period exists, but accounting standard differs.",
        )

    return ComparisonOutcome(
        status=ComparisonStatus.NOT_COMPARABLE,
        error_reason=missing_reason,
        value=None,
        reference_report_id=None,
        detail=default_detail,
    )


def _is_low_confidence(report: FinancialReport) -> bool:
    return report.extraction_confidence is not None and report.extraction_confidence < CONFIDENCE_THRESHOLD
