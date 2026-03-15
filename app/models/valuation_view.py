from decimal import Decimal

from sqlalchemy import Enum, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import PerDirection, ShortTermReaction
from app.models.mixins import TimestampMixin


class ValuationView(TimestampMixin, Base):
    __tablename__ = "valuation_views"
    __table_args__ = (UniqueConstraint("disclosure_id", name="uq_valuation_views_disclosure"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    disclosure_id: Mapped[int] = mapped_column(ForeignKey("disclosures.id"), index=True, nullable=False)
    last_close_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    last_per: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    last_pbr: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    eps_revision_potential: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    eps_revision_view: Mapped[str | None] = mapped_column(Text)
    acceptable_per_direction: Mapped[PerDirection | None] = mapped_column(
        Enum(PerDirection, native_enum=False)
    )
    per_change_view: Mapped[str | None] = mapped_column(Text)
    short_term_reaction: Mapped[ShortTermReaction | None] = mapped_column(
        Enum(ShortTermReaction, native_enum=False)
    )
    short_term_reaction_view: Mapped[str | None] = mapped_column(Text)
    valuation_comment: Mapped[str | None] = mapped_column(Text)

    disclosure = relationship("Disclosure", back_populates="valuation_views")
