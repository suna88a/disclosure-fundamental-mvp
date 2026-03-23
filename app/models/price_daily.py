from datetime import UTC, datetime, date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin


class PriceDaily(TimestampMixin, Base):
    __tablename__ = "price_daily"
    __table_args__ = (
        UniqueConstraint("code", "trade_date", name="uq_price_daily_code_trade_date"),
        Index("ix_price_daily_code_trade_date", "code", "trade_date"),
        Index("ix_price_daily_trade_date", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    close: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    adj_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
