from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import DisclosureCategory, DisclosurePriority
from app.models.mixins import TimestampMixin


class Disclosure(TimestampMixin, Base):
    __tablename__ = "disclosures"
    # TODO: If the source later publishes corrected versions under the same
    # timestamp/title, extend this table with a source version field and include
    # source_url in the dedupe strategy.
    __table_args__ = (
        UniqueConstraint(
            "source_name",
            "company_id",
            "disclosed_at",
            "title",
            name="uq_disclosures_source_company_time_title",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True, nullable=False)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown")
    disclosed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_title: Mapped[str | None] = mapped_column(String(500))
    classification_reason: Mapped[str | None] = mapped_column(Text)
    category: Mapped[DisclosureCategory | None] = mapped_column(
        Enum(DisclosureCategory, native_enum=False), index=True
    )
    priority: Mapped[DisclosurePriority | None] = mapped_column(
        Enum(DisclosurePriority, native_enum=False), index=True
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_disclosure_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_new: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_analysis_target: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    company = relationship("Company", back_populates="disclosures")
    pdf_files = relationship("PdfFile", back_populates="disclosure")
    financial_reports = relationship("FinancialReport", back_populates="disclosure")
    guidance_revisions = relationship("GuidanceRevision", back_populates="disclosure")
    dividend_revisions = relationship("DividendRevision", back_populates="disclosure")
    analysis_results = relationship("AnalysisResult", back_populates="disclosure")
    valuation_views = relationship("ValuationView", back_populates="disclosure")
    notifications = relationship("Notification", back_populates="disclosure")
