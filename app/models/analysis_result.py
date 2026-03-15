from decimal import Decimal

from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    ComparisonErrorReason,
    ComparisonStatus,
    RevisionDetectionStatus,
    ToneJudgement,
)
from app.models.mixins import TimestampMixin


class AnalysisResult(TimestampMixin, Base):
    __tablename__ = "analysis_results"
    # TODO: If comparison axes grow, move these per-axis fields to a dedicated
    # comparison_results table keyed by disclosure_id + comparison_axis.
    __table_args__ = (UniqueConstraint("disclosure_id", name="uq_analysis_results_disclosure"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    disclosure_id: Mapped[int] = mapped_column(ForeignKey("disclosures.id"), index=True, nullable=False)
    progress_judgement: Mapped[str | None] = mapped_column(Text)
    guidance_revision_status: Mapped[RevisionDetectionStatus | None] = mapped_column(
        Enum(RevisionDetectionStatus, native_enum=False)
    )
    guidance_revision_judgement: Mapped[str | None] = mapped_column(Text)
    dividend_revision_status: Mapped[RevisionDetectionStatus | None] = mapped_column(
        Enum(RevisionDetectionStatus, native_enum=False)
    )
    dividend_revision_judgement: Mapped[str | None] = mapped_column(Text)
    comment_tone: Mapped[ToneJudgement | None] = mapped_column(
        Enum(ToneJudgement, native_enum=False)
    )
    auto_summary: Mapped[str | None] = mapped_column(Text)
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    should_notify: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    yoy_comparison_status: Mapped[ComparisonStatus | None] = mapped_column(
        Enum(ComparisonStatus, native_enum=False)
    )
    yoy_comparison_error_reason: Mapped[ComparisonErrorReason | None] = mapped_column(
        Enum(ComparisonErrorReason, native_enum=False)
    )
    qoq_comparison_status: Mapped[ComparisonStatus | None] = mapped_column(
        Enum(ComparisonStatus, native_enum=False)
    )
    qoq_comparison_error_reason: Mapped[ComparisonErrorReason | None] = mapped_column(
        Enum(ComparisonErrorReason, native_enum=False)
    )
    average_progress_comparison_status: Mapped[ComparisonStatus | None] = mapped_column(
        Enum(ComparisonStatus, native_enum=False)
    )
    average_progress_comparison_error_reason: Mapped[ComparisonErrorReason | None] = mapped_column(
        Enum(ComparisonErrorReason, native_enum=False)
    )

    disclosure = relationship("Disclosure", back_populates="analysis_results")
