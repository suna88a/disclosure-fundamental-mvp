from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.fetchers.pdf_url_resolver import PdfUrlResolver
from app.models.enums import PdfDownloadStatus, PdfParseStatus
from app.repositories.pdf_repository import PdfRepository
from app.services.pdf_downloader import PdfDownloader
from app.services.pdf_target_selector import get_pdf_target_disclosures


def ingest_pdfs(
    session: Session,
    resolver: PdfUrlResolver,
    downloader: PdfDownloader,
    only_pending: bool = True,
) -> dict[str, int]:
    repository = PdfRepository(session)
    disclosures = get_pdf_target_disclosures(session, only_pending=only_pending)

    downloaded = 0
    skipped = 0
    failed = 0
    no_url = 0

    for disclosure in disclosures:
        resolution = resolver.resolve(disclosure)
        pdf_file = repository.create_or_get(disclosure.id, resolution.source_url)

        if resolution.source_url is None:
            repository.mark_no_url(pdf_file, resolution.resolution_reason)
            no_url += 1
            continue

        if pdf_file.file_path and Path(pdf_file.file_path).exists() and pdf_file.file_hash:
            pdf_file.download_status = PdfDownloadStatus.SKIPPED
            pdf_file.download_error_message = "Skipped because an existing local file is available."
            session.add(pdf_file)
            skipped += 1
            continue

        try:
            downloaded_pdf = downloader.download(resolution.source_url, disclosure.id)
            pdf_file.file_path = downloaded_pdf.file_path
            pdf_file.file_hash = downloaded_pdf.file_hash
            pdf_file.download_status = PdfDownloadStatus.DOWNLOADED
            pdf_file.download_error_message = None
            pdf_file.downloaded_at = datetime.now(UTC)
            pdf_file.parse_status = PdfParseStatus.PENDING
            session.add(pdf_file)
            downloaded += 1
        except Exception as exc:
            pdf_file.download_status = PdfDownloadStatus.FAILED
            pdf_file.download_error_message = f"{resolution.resolution_reason} Download failed: {exc}"
            session.add(pdf_file)
            failed += 1

    session.flush()
    session.expire_all()
    return {
        "processed": len(disclosures),
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "no_url": no_url,
    }
