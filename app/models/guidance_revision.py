from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import RevisionDirection
from app.models.mixins import TimestampMixin


class GuidanceRevision(TimestampMixin, Base):
    __tablename__ = "guidance_revisions"
    __table_args__ = (UniqueConstraint("disclosure_id", name="uq_guidance_revisions_disclosure"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    disclosure_id: Mapped[int] = mapped_column(ForeignKey("disclosures.id"), index=True, nullable=False)
    revised_sales_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    revised_sales_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    revised_operating_income_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    revised_operating_income_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    revised_ordinary_income_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    revised_ordinary_income_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    revised_net_income_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    revised_net_income_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    revised_eps_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    revised_eps_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    revision_rate_operating_income: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    revision_direction: Mapped[RevisionDirection | None] = mapped_column(
        Enum(RevisionDirection, native_enum=False)
    )

    disclosure = relationship("Disclosure", back_populates="guidance_revisions")
