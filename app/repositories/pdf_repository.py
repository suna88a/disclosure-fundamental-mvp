from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PdfDownloadStatus
from app.models.pdf_file import PdfFile


class PdfRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_disclosure_and_url(self, disclosure_id: int, source_url: str | None) -> PdfFile | None:
        if source_url is None:
            statement = select(PdfFile).where(
                PdfFile.disclosure_id == disclosure_id,
                PdfFile.source_url.is_(None),
            )
            return self.session.scalar(statement)

        statement = select(PdfFile).where(
            PdfFile.disclosure_id == disclosure_id,
            PdfFile.source_url == source_url,
        )
        return self.session.scalar(statement)

    def create_or_get(self, disclosure_id: int, source_url: str | None) -> PdfFile:
        existing = self.find_by_disclosure_and_url(disclosure_id, source_url)
        if existing is not None:
            return existing

        pdf_file = PdfFile(disclosure_id=disclosure_id, source_url=source_url)
        self.session.add(pdf_file)
        self.session.flush()
        return pdf_file

    def mark_no_url(self, pdf_file: PdfFile, message: str) -> PdfFile:
        pdf_file.download_status = PdfDownloadStatus.NO_URL
        pdf_file.download_error_message = message
        self.session.add(pdf_file)
        self.session.flush()
        return pdf_file
