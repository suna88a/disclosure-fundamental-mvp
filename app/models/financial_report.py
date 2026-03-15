from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import CumulativeType, PeriodType, StatementScope
from app.models.mixins import TimestampMixin


class FinancialReport(TimestampMixin, Base):
    __tablename__ = "financial_reports"
    __table_args__ = (UniqueConstraint("disclosure_id", name="uq_financial_reports_disclosure"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    disclosure_id: Mapped[int] = mapped_column(ForeignKey("disclosures.id"), index=True, nullable=False)
    pdf_file_id: Mapped[int | None] = mapped_column(ForeignKey("pdf_files.id"), index=True)
    accounting_standard: Mapped[str | None] = mapped_column(String(50))
    period_type: Mapped[PeriodType | None] = mapped_column(Enum(PeriodType, native_enum=False))
    statement_scope: Mapped[StatementScope | None] = mapped_column(
        Enum(StatementScope, native_enum=False)
    )
    cumulative_type: Mapped[CumulativeType | None] = mapped_column(
        Enum(CumulativeType, native_enum=False)
    )
    sales: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    operating_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    ordinary_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    eps: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    company_forecast_sales: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    company_forecast_operating_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    company_forecast_ordinary_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    company_forecast_net_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    company_forecast_eps: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    progress_rate_operating_income: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    extraction_version: Mapped[str] = mapped_column(String(50), default="v1", nullable=False)

    disclosure = relationship("Disclosure", back_populates="financial_reports")
    pdf_file = relationship("PdfFile", back_populates="financial_reports")
