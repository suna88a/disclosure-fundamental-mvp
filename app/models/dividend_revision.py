from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import RevisionDirection
from app.models.mixins import TimestampMixin


class DividendRevision(TimestampMixin, Base):
    __tablename__ = "dividend_revisions"
    __table_args__ = (UniqueConstraint("disclosure_id", name="uq_dividend_revisions_disclosure"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    disclosure_id: Mapped[int] = mapped_column(ForeignKey("disclosures.id"), index=True, nullable=False)
    interim_dividend_before: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    interim_dividend_after: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    year_end_dividend_before: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    year_end_dividend_after: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    annual_dividend_before: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    annual_dividend_after: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    revision_direction: Mapped[RevisionDirection | None] = mapped_column(
        Enum(RevisionDirection, native_enum=False)
    )

    disclosure = relationship("Disclosure", back_populates="dividend_revisions")
