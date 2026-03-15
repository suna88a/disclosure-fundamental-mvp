from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.company import Company
from app.fetchers.financial_report_parser import FinancialReportParser
from app.models.disclosure import Disclosure
from app.models.enums import (
    DisclosureCategory,
    PdfDownloadStatus,
    PdfParseErrorCode,
    PdfParseStatus,
)
from app.models.pdf_file import PdfFile
from app.repositories.financial_report_repository import FinancialReportRepository
from app.services.financial_report_extractor import build_financial_report_payload


TARGET_CATEGORY = DisclosureCategory.EARNINGS_REPORT


def ingest_financial_reports(session: Session, parser: FinancialReportParser) -> dict[str, int]:
    statement = (
        select(PdfFile)
        .join(PdfFile.disclosure)
        .join(Disclosure.company)
        .options(selectinload(PdfFile.disclosure))
        .where(
            Company.is_active.is_(True),
            Disclosure.category == TARGET_CATEGORY,
            Disclosure.is_analysis_target.is_(True),
            PdfFile.download_status == PdfDownloadStatus.DOWNLOADED,
            PdfFile.file_path.is_not(None),
            PdfFile.parse_status.in_((PdfParseStatus.PENDING, PdfParseStatus.FAILED)),
        )
    )
    pdf_files = list(session.scalars(statement))

    repository = FinancialReportRepository(session)
    extracted = 0
    unsupported = 0
    failed = 0

    for pdf_file in pdf_files:
        pdf_file.parse_status = PdfParseStatus.PROCESSING
        session.add(pdf_file)
        session.flush()

        try:
            parsed = parser.parse(pdf_file)
            if not parsed.supported:
                pdf_file.parse_status = PdfParseStatus.FAILED
                pdf_file.parse_error_code = parsed.error_code or PdfParseErrorCode.UNKNOWN
                pdf_file.parse_error_message = parsed.support_reason
                unsupported += 1
                session.add(pdf_file)
                continue

            payload = build_financial_report_payload(parsed, pdf_file.id)
            repository.upsert(pdf_file.disclosure_id, **payload)
            pdf_file.parse_status = PdfParseStatus.COMPLETED
            pdf_file.parse_error_code = None
            pdf_file.parse_error_message = None
            session.add(pdf_file)
            extracted += 1
        except FileNotFoundError as exc:
            pdf_file.parse_status = PdfParseStatus.FAILED
            pdf_file.parse_error_code = PdfParseErrorCode.FILE_NOT_FOUND
            pdf_file.parse_error_message = f"Financial report extraction failed: {exc}"
            session.add(pdf_file)
            failed += 1
        except TimeoutError as exc:
            pdf_file.parse_status = PdfParseStatus.FAILED
            pdf_file.parse_error_code = PdfParseErrorCode.TIMEOUT
            pdf_file.parse_error_message = f"Financial report extraction failed: {exc}"
            session.add(pdf_file)
            failed += 1
        except Exception as exc:
            pdf_file.parse_status = PdfParseStatus.FAILED
            pdf_file.parse_error_code = PdfParseErrorCode.UNKNOWN
            pdf_file.parse_error_message = f"Financial report extraction failed: {exc}"
            session.add(pdf_file)
            failed += 1

    session.flush()
    session.expire_all()
    return {
        "processed": len(pdf_files),
        "extracted": extracted,
        "unsupported": unsupported,
        "failed": failed,
    }
