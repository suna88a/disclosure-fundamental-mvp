from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import PdfDownloadStatus, PdfParseErrorCode, PdfParseStatus
from app.models.mixins import TimestampMixin


class PdfFile(TimestampMixin, Base):
    __tablename__ = "pdf_files"
    __table_args__ = (
        UniqueConstraint("disclosure_id", "source_url", name="uq_pdf_files_disclosure_source_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    disclosure_id: Mapped[int] = mapped_column(ForeignKey("disclosures.id"), index=True, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    file_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    download_status: Mapped[PdfDownloadStatus] = mapped_column(
        Enum(PdfDownloadStatus, native_enum=False),
        default=PdfDownloadStatus.PENDING,
        nullable=False,
    )
    download_error_message: Mapped[str | None] = mapped_column(Text)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parse_status: Mapped[PdfParseStatus] = mapped_column(
        Enum(PdfParseStatus, native_enum=False),
        default=PdfParseStatus.PENDING,
        nullable=False,
    )
    parse_error_code: Mapped[PdfParseErrorCode | None] = mapped_column(
        Enum(PdfParseErrorCode, native_enum=False),
        nullable=True,
    )
    parse_error_message: Mapped[str | None] = mapped_column(Text)

    disclosure = relationship("Disclosure", back_populates="pdf_files")
    financial_reports = relationship("FinancialReport", back_populates="pdf_file")
