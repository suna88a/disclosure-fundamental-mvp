from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory, PdfDownloadStatus


TARGET_CATEGORIES = (
    DisclosureCategory.EARNINGS_REPORT,
    DisclosureCategory.GUIDANCE_REVISION,
    DisclosureCategory.DIVIDEND_REVISION,
    DisclosureCategory.SHARE_BUYBACK,
)


def get_pdf_target_disclosures(session: Session, only_pending: bool = True) -> list[Disclosure]:
    statement = (
        select(Disclosure)
        .join(Disclosure.company)
        .options(selectinload(Disclosure.pdf_files))
        .where(
            Company.is_active.is_(True),
            Disclosure.is_analysis_target.is_(True),
            Disclosure.category.in_(TARGET_CATEGORIES),
        )
    )
    disclosures = list(session.scalars(statement))
    if not only_pending:
        return disclosures

    pending: list[Disclosure] = []
    for disclosure in disclosures:
        if not disclosure.pdf_files:
            pending.append(disclosure)
            continue

        if any(
            pdf.download_status in {PdfDownloadStatus.PENDING, PdfDownloadStatus.FAILED}
            for pdf in disclosure.pdf_files
        ):
            pending.append(disclosure)
            continue

        if all(
            pdf.download_status == PdfDownloadStatus.NO_URL and pdf.file_path is None
            for pdf in disclosure.pdf_files
        ):
            continue

        if all(pdf.file_path is None for pdf in disclosure.pdf_files):
            pending.append(disclosure)

    return pending
