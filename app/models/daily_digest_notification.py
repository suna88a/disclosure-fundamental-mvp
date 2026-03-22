from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import NotificationChannel, NotificationStatus, NotificationType
from app.models.mixins import TimestampMixin


def _enum_values(enum_cls):
    return [member.value for member in enum_cls]


class DailyDigestNotification(TimestampMixin, Base):
    __tablename__ = "daily_digest_notifications"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_daily_digest_notifications_dedupe_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, native_enum=False, values_callable=_enum_values),
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False, values_callable=_enum_values),
        nullable=False,
    )
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, native_enum=False, values_callable=_enum_values),
        default=NotificationStatus.PENDING.value,
        nullable=False,
    )
    message_count: Mapped[int] = mapped_column(nullable=False, default=0)
    external_message_id: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
