from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.analysis_result import AnalysisResult
from app.models.disclosure import Disclosure
from app.models.enums import (
    ComparisonErrorReason,
    ComparisonStatus,
    PdfParseErrorCode,
    PdfParseStatus,
)
from app.models.pdf_file import PdfFile


@dataclass(frozen=True)
class ComparisonFailureSummary:
    total: Counter[str]
    yoy: Counter[str]
    qoq: Counter[str]
    average_progress: Counter[str]


@dataclass(frozen=True)
class PdfParseFailureSummary:
    total_failed: int
    reasons: Counter[str]


@dataclass(frozen=True)
class PdfParseFailureSample:
    disclosure_id: int
    company_code: str
    company_name: str
    title: str
    parse_error_code: str
    parse_error_message: str | None
    file_path: str | None
    source_url: str | None


@dataclass(frozen=True)
class PdfParseFailureSamplesReport:
    reason_counts: Counter[str]
    samples_by_code: dict[str, list[PdfParseFailureSample]]



def summarize_comparison_errors(session: Session) -> ComparisonFailureSummary:
    results = list(
        session.scalars(
            select(AnalysisResult).where(
                AnalysisResult.yoy_comparison_status.is_not(None)
                | AnalysisResult.qoq_comparison_status.is_not(None)
                | AnalysisResult.average_progress_comparison_status.is_not(None)
            )
        )
    )

    total = Counter[str]()
    yoy = Counter[str]()
    qoq = Counter[str]()
    average_progress = Counter[str]()

    for result in results:
        _collect_comparison_reason(
            counter=total,
            axis_counter=yoy,
            status=result.yoy_comparison_status,
            reason=result.yoy_comparison_error_reason,
        )
        _collect_comparison_reason(
            counter=total,
            axis_counter=qoq,
            status=result.qoq_comparison_status,
            reason=result.qoq_comparison_error_reason,
        )
        _collect_comparison_reason(
            counter=total,
            axis_counter=average_progress,
            status=result.average_progress_comparison_status,
            reason=result.average_progress_comparison_error_reason,
        )

    return ComparisonFailureSummary(
        total=total,
        yoy=yoy,
        qoq=qoq,
        average_progress=average_progress,
    )



def summarize_pdf_parse_failures(session: Session) -> PdfParseFailureSummary:
    pdf_files = list(
        session.scalars(
            select(PdfFile).where(PdfFile.parse_status == PdfParseStatus.FAILED)
        )
    )
    reasons = Counter[str]()
    for pdf_file in pdf_files:
        reasons[_normalize_parse_failure_reason(pdf_file.parse_error_code, pdf_file.parse_error_message)] += 1
    return PdfParseFailureSummary(total_failed=len(pdf_files), reasons=reasons)



def collect_pdf_parse_failure_samples(
    session: Session,
    *,
    code: str | None = None,
    limit: int = 5,
) -> PdfParseFailureSamplesReport:
    statement = (
        select(PdfFile)
        .options(joinedload(PdfFile.disclosure).joinedload(Disclosure.company))
        .where(PdfFile.parse_status == PdfParseStatus.FAILED)
        .order_by(PdfFile.id.desc())
    )
    pdf_files = list(session.scalars(statement))

    reason_counts = Counter[str]()
    grouped_samples: dict[str, list[PdfParseFailureSample]] = defaultdict(list)
    target_code = code.strip().lower() if code else None

    for pdf_file in pdf_files:
        normalized_code = _normalize_parse_failure_reason(pdf_file.parse_error_code, pdf_file.parse_error_message)
        reason_counts[normalized_code] += 1
        if target_code and normalized_code != target_code:
            continue
        if len(grouped_samples[normalized_code]) >= limit:
            continue

        disclosure = pdf_file.disclosure
        company = disclosure.company
        grouped_samples[normalized_code].append(
            PdfParseFailureSample(
                disclosure_id=disclosure.id,
                company_code=company.code,
                company_name=company.name_ja or company.name,
                title=disclosure.title,
                parse_error_code=normalized_code,
                parse_error_message=pdf_file.parse_error_message,
                file_path=pdf_file.file_path,
                source_url=pdf_file.source_url,
            )
        )

    ordered_samples: dict[str, list[PdfParseFailureSample]] = {}
    ordered_codes = [target_code] if target_code else [key for key, _ in reason_counts.most_common()]
    for reason_code in ordered_codes:
        if reason_code and reason_code in grouped_samples:
            ordered_samples[reason_code] = grouped_samples[reason_code]

    return PdfParseFailureSamplesReport(
        reason_counts=reason_counts,
        samples_by_code=ordered_samples,
    )



def _collect_comparison_reason(
    *,
    counter: Counter[str],
    axis_counter: Counter[str],
    status: ComparisonStatus | None,
    reason: ComparisonErrorReason | None,
) -> None:
    if status == ComparisonStatus.OK:
        return
    if reason is None or reason == ComparisonErrorReason.NONE:
        return
    label = reason.value
    counter[label] += 1
    axis_counter[label] += 1



def _normalize_parse_failure_reason(
    error_code: PdfParseErrorCode | None,
    message: str | None,
) -> str:
    if error_code is not None:
        return error_code.value
    if message is None or not message.strip():
        return "empty_reason"

    normalized = message.strip()
    if normalized.startswith("Financial report extraction failed:"):
        normalized = normalized.split(":", 1)[1].strip()

    lowered = normalized.lower()
    if "unsupported" in lowered or "not supported" in lowered:
        return "unsupported_format"
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "file not found" in lowered:
        return "file_not_found"

    first_line = normalized.splitlines()[0].strip()
    return first_line[:80]



def render_failure_summary(
    comparison_summary: ComparisonFailureSummary,
    pdf_summary: PdfParseFailureSummary,
) -> str:
    lines: list[str] = []
    lines.append("Comparison Error Summary")
    lines.append(f"  total_failure_axes: {sum(comparison_summary.total.values())}")
    lines.extend(_render_counter_block("  total", comparison_summary.total))
    lines.extend(_render_counter_block("  yoy", comparison_summary.yoy))
    lines.extend(_render_counter_block("  qoq", comparison_summary.qoq))
    lines.extend(_render_counter_block("  average_progress", comparison_summary.average_progress))
    lines.append("")
    lines.append("PDF Parse Failure Summary")
    lines.append(f"  total_failed_pdfs: {pdf_summary.total_failed}")
    lines.extend(_render_counter_block("  reasons", pdf_summary.reasons))
    return "\n".join(lines)



def render_pdf_parse_failure_samples(report: PdfParseFailureSamplesReport) -> str:
    lines: list[str] = []
    lines.append("PDF Parse Failure Samples")
    if not report.reason_counts:
        lines.append("  no failed pdfs")
        return "\n".join(lines)

    lines.append("  counts:")
    for reason_code, count in report.reason_counts.most_common():
        lines.append(f"    {reason_code}: {count}")

    for reason_code, samples in report.samples_by_code.items():
        lines.append("")
        lines.append(f"  [{reason_code}] top {len(samples)} sample(s)")
        for sample in samples:
            lines.append(
                f"    disclosure_id={sample.disclosure_id} / {sample.company_code} {sample.company_name}"
            )
            lines.append(f"      title: {sample.title}")
            lines.append(f"      file_path: {sample.file_path or '-'}")
            lines.append(f"      source_url: {sample.source_url or '-'}")
            lines.append(f"      message: {sample.parse_error_message or '-'}")
    return "\n".join(lines)



def _render_counter_block(title: str, counter: Counter[str]) -> list[str]:
    lines = [title + ":"]
    if not counter:
        lines.append("    none")
        return lines
    for key, count in counter.most_common():
        lines.append(f"    {key}: {count}")
    return lines
