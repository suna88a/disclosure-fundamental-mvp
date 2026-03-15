from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from decimal import ROUND_HALF_UP
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import (
    ComparisonErrorReason,
    ComparisonStatus,
    CumulativeType,
    DisclosureCategory,
    DisclosurePriority,
    JobStatus,
    NotificationStatus,
    PeriodType,
    PdfDownloadStatus,
    PdfParseStatus,
    RevisionDetectionStatus,
    RevisionDirection,
    StatementScope,
    ToneJudgement,
)
from app.models.job_run import JobRun
from app.models.notification import Notification


@dataclass(frozen=True)
class DisclosureListItem:
    disclosure_id: int
    disclosed_at_label: str
    company_code: str
    company_name: str
    category_label: str
    priority_label: str
    summary: str


@dataclass(frozen=True)
class NotificationListItem:
    sent_at_label: str
    company_code: str
    company_name: str
    category_label: str
    status_label: str
    summary: str
    detail_url: str


@dataclass(frozen=True)
class JobStatusItem:
    job_name: str
    started_at_label: str
    finished_at_label: str
    status_label: str
    processed_count_label: str
    result_summary_label: str | None
    error_message: str | None
    last_success_at_label: str


def list_recent_disclosures(session: Session, limit: int = 50) -> list[DisclosureListItem]:
    statement = (
        select(Disclosure)
        .options(
            selectinload(Disclosure.company),
            selectinload(Disclosure.analysis_results),
        )
        .order_by(Disclosure.disclosed_at.desc())
        .limit(limit)
    )
    disclosures = list(session.scalars(statement))
    items: list[DisclosureListItem] = []
    for disclosure in disclosures:
        analysis = disclosure.analysis_results[0] if disclosure.analysis_results else None
        items.append(
            DisclosureListItem(
                disclosure_id=disclosure.id,
                disclosed_at_label=_format_datetime(disclosure.disclosed_at),
                company_code=disclosure.company.code,
                company_name=company_display_name(disclosure.company),
                category_label=_category_label(disclosure.category),
                priority_label=_priority_label(disclosure.priority),
                summary=_summary_text(analysis),
            )
        )
    return items


def get_disclosure_detail(session: Session, disclosure_id: int) -> Disclosure | None:
    statement = (
        select(Disclosure)
        .options(
            selectinload(Disclosure.company),
            selectinload(Disclosure.pdf_files),
            selectinload(Disclosure.financial_reports),
            selectinload(Disclosure.guidance_revisions),
            selectinload(Disclosure.dividend_revisions),
            selectinload(Disclosure.analysis_results),
            selectinload(Disclosure.valuation_views),
            selectinload(Disclosure.notifications),
        )
        .where(Disclosure.id == disclosure_id)
    )
    return session.scalar(statement)


def list_notifications(session: Session, limit: int = 100) -> list[NotificationListItem]:
    statement = (
        select(Notification)
        .join(Notification.disclosure)
        .options(
            selectinload(Notification.disclosure).selectinload(Disclosure.company),
        )
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    notifications = list(session.scalars(statement))
    items: list[NotificationListItem] = []
    for notification in notifications:
        disclosure = notification.disclosure
        items.append(
            NotificationListItem(
                sent_at_label=format_datetime(notification.sent_at or notification.created_at),
                company_code=disclosure.company.code,
                company_name=company_display_name(disclosure.company),
                category_label=_category_label(disclosure.category),
                status_label=notification_status_label(notification.status),
                summary=_notification_summary(notification.body),
                detail_url=f"/disclosures/{disclosure.id}",
            )
        )
    return items


def list_job_statuses(session: Session) -> list[JobStatusItem]:
    subquery = (
        select(JobRun.job_name, func.max(JobRun.id).label("latest_id"))
        .group_by(JobRun.job_name)
        .subquery()
    )
    latest_runs = list(
        session.scalars(select(JobRun).join(subquery, JobRun.id == subquery.c.latest_id).order_by(JobRun.job_name))
    )
    items: list[JobStatusItem] = []
    for job_run in latest_runs:
        last_success = session.scalar(
            select(JobRun.finished_at)
            .where(JobRun.job_name == job_run.job_name, JobRun.status == JobStatus.SUCCESS)
            .order_by(JobRun.finished_at.desc())
            .limit(1)
        )
        items.append(
            JobStatusItem(
                job_name=job_run.job_name,
                started_at_label=format_datetime(job_run.started_at),
                finished_at_label=format_datetime(job_run.finished_at),
                status_label=job_status_label(job_run.status),
                processed_count_label=str(job_run.processed_count),
                result_summary_label=_job_result_summary_label(job_run.result_summary_json),
                error_message=_truncate_text(job_run.error_message, 120),
                last_success_at_label=format_datetime(last_success),
            )
        )
    return items


def category_label(category: DisclosureCategory | None) -> str:
    return _category_label(category)


def company_display_name(company: Company) -> str:
    if company.name_ja and company.name_ja.strip():
        return company.name_ja.strip()
    return company.name.strip()


def priority_label(priority: DisclosurePriority | None) -> str:
    return _priority_label(priority)


def download_status_label(status: PdfDownloadStatus | None) -> str:
    mapping = {
        PdfDownloadStatus.PENDING: "取得待ち",
        PdfDownloadStatus.DOWNLOADED: "取得済み",
        PdfDownloadStatus.FAILED: "取得失敗",
        PdfDownloadStatus.NO_URL: "URL未確認",
        PdfDownloadStatus.SKIPPED: "再取得不要",
    }
    return mapping.get(status, "不明")


def parse_status_label(status: PdfParseStatus | None) -> str:
    mapping = {
        PdfParseStatus.PENDING: "未解析",
        PdfParseStatus.PROCESSING: "解析中",
        PdfParseStatus.COMPLETED: "解析済み",
        PdfParseStatus.FAILED: "解析失敗",
    }
    return mapping.get(status, "不明")


def notification_status_label(status: NotificationStatus | None) -> str:
    mapping = {
        NotificationStatus.PENDING: "送信待ち",
        NotificationStatus.SENT: "送信済み",
        NotificationStatus.FAILED: "送信失敗",
        NotificationStatus.SKIPPED: "送信対象外",
    }
    return mapping.get(status, "不明")


def job_status_label(status: JobStatus | None) -> str:
    mapping = {
        JobStatus.RUNNING: "実行中",
        JobStatus.SUCCESS: "成功",
        JobStatus.FAILED: "失敗",
    }
    return mapping.get(status, "不明")


def period_type_label(value: PeriodType | None) -> str:
    mapping = {
        PeriodType.Q1: "第1四半期",
        PeriodType.Q2: "第2四半期",
        PeriodType.Q3: "第3四半期",
        PeriodType.FY: "通期",
    }
    return mapping.get(value, "未解析")


def statement_scope_label(value: StatementScope | None) -> str:
    mapping = {
        StatementScope.CONSOLIDATED: "連結",
        StatementScope.NON_CONSOLIDATED: "個別",
    }
    return mapping.get(value, "未解析")


def cumulative_type_label(value: CumulativeType | None) -> str:
    mapping = {
        CumulativeType.CUMULATIVE: "累計",
        CumulativeType.QUARTERLY_ONLY: "四半期単独",
    }
    return mapping.get(value, "未解析")


def revision_direction_label(value: RevisionDirection | None) -> str:
    mapping = {
        RevisionDirection.UP: "上方修正",
        RevisionDirection.DOWN: "下方修正",
        RevisionDirection.UNCHANGED: "据え置き",
        RevisionDirection.NOT_AVAILABLE: "判定保留",
    }
    return mapping.get(value, "該当なし")


def tone_label(value: ToneJudgement | None) -> str:
    mapping = {
        ToneJudgement.POSITIVE: "前向き",
        ToneJudgement.NEUTRAL: "中立",
        ToneJudgement.NEGATIVE: "慎重",
        ToneJudgement.UNKNOWN: "未判定",
    }
    return mapping.get(value, "未判定")


def comparison_label(status: ComparisonStatus | None, reason: ComparisonErrorReason | None) -> str:
    if status == ComparisonStatus.OK:
        return "比較済み"
    if status == ComparisonStatus.NEEDS_REVIEW:
        return f"要確認 ({comparison_reason_label(reason)})"
    if status == ComparisonStatus.NOT_COMPARABLE:
        return f"比較不可 ({comparison_reason_label(reason)})"
    return "未判定"


def comparison_reason_label(reason: ComparisonErrorReason | None) -> str:
    mapping = {
        ComparisonErrorReason.NONE: "比較可能",
        ComparisonErrorReason.INSUFFICIENT_HISTORY: "過去データ不足",
        ComparisonErrorReason.SCOPE_MISMATCH: "連結・個別の不一致",
        ComparisonErrorReason.CUMULATIVE_MISMATCH: "累計・単独の不一致",
        ComparisonErrorReason.Q1_QOQ_NOT_APPLICABLE: "第1四半期のため比較対象外",
        ComparisonErrorReason.ACCOUNTING_STANDARD_MISMATCH: "会計基準の差異",
        ComparisonErrorReason.EXTRACTION_CONFIDENCE_LOW: "抽出精度が不足",
    }
    return mapping.get(reason, "理由未設定")


def revision_detection_label(status: RevisionDetectionStatus | None, target: str) -> str:
    if target == "guidance":
        mapping = {
            RevisionDetectionStatus.UNCHANGED_DETECTED: "会社予想は据え置き",
            RevisionDetectionStatus.NO_REVISION_DETECTED: "業績予想の修正は確認されず",
            RevisionDetectionStatus.REVISION_DETECTED_UP: "業績予想の上方修正を確認",
            RevisionDetectionStatus.REVISION_DETECTED_DOWN: "業績予想の下方修正を確認",
            RevisionDetectionStatus.REVISION_DETECTED_OTHER: "業績予想の修正を確認",
        }
    else:
        mapping = {
            RevisionDetectionStatus.UNCHANGED_DETECTED: "配当予想は据え置き",
            RevisionDetectionStatus.NO_REVISION_DETECTED: "配当予想の修正は確認されず",
            RevisionDetectionStatus.REVISION_DETECTED_UP: "配当予想の増額修正を確認",
            RevisionDetectionStatus.REVISION_DETECTED_DOWN: "配当予想の減額修正を確認",
            RevisionDetectionStatus.REVISION_DETECTED_OTHER: "配当予想の修正を確認",
        }
    return mapping.get(status, "未判定")


def yes_no_label(value: bool | None) -> str:
    if value is True:
        return "はい"
    if value is False:
        return "いいえ"
    return "未判定"


def format_decimal(value: Decimal | None, suffix: str = "") -> str:
    if value is None:
        return "未解析"
    decimals = 1 if suffix in {"%", "pt"} else 0
    return f"{_format_number(value, decimals)}{suffix}"


def format_score(value: Decimal | None) -> str:
    if value is None:
        return "未算出"
    return _format_number(value, 1)


def format_text(value: str | None, missing: str = "未解析") -> str:
    if value is None or not value.strip():
        return missing
    return value


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "不明"
    return _format_datetime(value)


def notification_anchor(disclosure_id: int) -> str:
    return f"/disclosures/{disclosure_id}#notifications"


def _summary_text(analysis: AnalysisResult | None) -> str:
    if analysis is None or not analysis.auto_summary:
        return "未解析"
    return analysis.auto_summary


def _format_datetime(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def _notification_summary(body: str) -> str:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("要点:"):
            return _truncate_text(line.replace("要点:", "", 1).strip(), 100) or "本文なし"
    if len(lines) >= 3:
        return _truncate_text(lines[2], 100) or "本文なし"
    return _truncate_text(body, 100) or "本文なし"


def _category_label(category: DisclosureCategory | None) -> str:
    mapping = {
        DisclosureCategory.EARNINGS_REPORT: "決算短信",
        DisclosureCategory.GUIDANCE_REVISION: "業績予想の修正",
        DisclosureCategory.DIVIDEND_REVISION: "配当予想の修正",
        DisclosureCategory.SHARE_BUYBACK: "自社株買い",
        DisclosureCategory.OTHER: "その他",
        DisclosureCategory.UNKNOWN: "未分類",
    }
    return mapping.get(category, "未分類")


def _priority_label(priority: DisclosurePriority | None) -> str:
    mapping = {
        DisclosurePriority.CRITICAL: "最優先",
        DisclosurePriority.HIGH: "高",
        DisclosurePriority.MEDIUM: "中",
        DisclosurePriority.LOW: "低",
    }
    return mapping.get(priority, "未設定")


def _format_number(value: Decimal, decimals: int) -> str:
    if decimals <= 0:
        quantized = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return f"{int(quantized):,}"
    quantize_pattern = "1." + ("0" * decimals)
    quantized = value.quantize(Decimal(quantize_pattern), rounding=ROUND_HALF_UP)
    return f"{quantized:,.{decimals}f}"


def _truncate_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _job_result_summary_label(result_summary_json: str | None) -> str | None:
    if not result_summary_json:
        return None
    try:
        payload = json.loads(result_summary_json)
    except json.JSONDecodeError:
        return _truncate_text(result_summary_json, 120)
    if not isinstance(payload, dict):
        return None

    priority_keys = [
        ("inserted", "inserted"),
        ("updated", "updated"),
        ("skipped", "skipped"),
        ("skipped_inactive", "inactive"),
        ("downloaded", "downloaded"),
        ("failed", "failed"),
        ("no_url", "no_url"),
        ("extracted", "extracted"),
        ("unsupported", "unsupported"),
        ("analysis_saved", "analysis"),
        ("sent", "sent"),
        ("saved", "saved"),
    ]
    parts: list[str] = []
    for key, label in priority_keys:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        parts.append(f"{label} {value}")
        if len(parts) >= 4:
            break

    if not parts:
        for key, value in payload.items():
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            parts.append(f"{key} {value}")
            if len(parts) >= 4:
                break

    if not parts:
        return None
    return " / ".join(parts)
