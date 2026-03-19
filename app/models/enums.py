from enum import StrEnum


class DisclosureCategory(StrEnum):
    EARNINGS_REPORT = "earnings_report"
    GUIDANCE_REVISION = "guidance_revision"
    DIVIDEND_REVISION = "dividend_revision"
    SHARE_BUYBACK = "share_buyback"
    OTHER = "other"
    UNKNOWN = "unknown"


class DisclosurePriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class JobStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class PdfParseStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PdfParseErrorCode(StrEnum):
    UNSUPPORTED_FORMAT = "unsupported_format"
    MANIFEST_ENTRY_MISSING = "manifest_entry_missing"
    PARSE_TARGET_MISSING = "parse_target_missing"
    PERIOD_DETECTION_FAILED = "period_detection_failed"
    SCOPE_DETECTION_FAILED = "scope_detection_failed"
    CUMULATIVE_TYPE_DETECTION_FAILED = "cumulative_type_detection_failed"
    FORECAST_SECTION_MISSING = "forecast_section_missing"
    VALUE_NOT_FOUND = "value_not_found"
    FILE_NOT_FOUND = "file_not_found"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class PdfDownloadStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    FAILED = "failed"
    NO_URL = "no_url"
    SKIPPED = "skipped"


class PeriodType(StrEnum):
    Q1 = "1Q"
    Q2 = "2Q"
    Q3 = "3Q"
    FY = "FY"


class StatementScope(StrEnum):
    CONSOLIDATED = "consolidated"
    NON_CONSOLIDATED = "non_consolidated"


class CumulativeType(StrEnum):
    CUMULATIVE = "cumulative"
    QUARTERLY_ONLY = "quarterly_only"


class RevisionDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    UNCHANGED = "unchanged"
    NOT_AVAILABLE = "not_available"


class ToneJudgement(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class RevisionDetectionStatus(StrEnum):
    UNCHANGED_DETECTED = "unchanged_detected"
    NO_REVISION_DETECTED = "no_revision_detected"
    REVISION_DETECTED_UP = "revision_detected_up"
    REVISION_DETECTED_DOWN = "revision_detected_down"
    REVISION_DETECTED_OTHER = "revision_detected_other"


class ComparisonStatus(StrEnum):
    OK = "ok"
    NOT_COMPARABLE = "not_comparable"
    NEEDS_REVIEW = "needs_review"


class ComparisonErrorReason(StrEnum):
    NONE = "none"
    INSUFFICIENT_HISTORY = "insufficient_history"
    SCOPE_MISMATCH = "scope_mismatch"
    CUMULATIVE_MISMATCH = "cumulative_mismatch"
    Q1_QOQ_NOT_APPLICABLE = "q1_qoq_not_applicable"
    ACCOUNTING_STANDARD_MISMATCH = "accounting_standard_mismatch"
    EXTRACTION_CONFIDENCE_LOW = "extraction_confidence_low"


class PerDirection(StrEnum):
    EXPAND = "expand"
    CONTRACT = "contract"
    STABLE = "stable"
    UNKNOWN = "unknown"


class ShortTermReaction(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationChannel(StrEnum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    DUMMY = "dummy"


class NotificationType(StrEnum):
    ANALYSIS_ALERT = "analysis_alert"
    RAW_DISCLOSURE_BATCH = "raw_disclosure_batch"
    DAILY_RAW_DIGEST = "daily_raw_digest"
