from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.daily_digest_notification import DailyDigestNotification
from app.models.enums import NotificationStatus


class DailyDigestNotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_dedupe_key(self, dedupe_key: str) -> DailyDigestNotification | None:
        return self.session.scalar(
            select(DailyDigestNotification).where(DailyDigestNotification.dedupe_key == dedupe_key)
        )

    def prepare_pending(
        self,
        *,
        notification_type: str,
        channel: str,
        destination: str,
        target_date: date,
        dedupe_key: str,
        body: str,
        force: bool = False,
    ) -> DailyDigestNotification | None:
        existing = self.get_by_dedupe_key(dedupe_key)
        if existing is not None:
            if existing.status == NotificationStatus.SENT.value and not force:
                return None
            return self._reuse_existing(
                existing,
                notification_type=notification_type,
                channel=channel,
                destination=destination,
                target_date=target_date,
                dedupe_key=dedupe_key,
                body=body,
            )

        created = self._try_create_pending(
            notification_type=notification_type,
            channel=channel,
            destination=destination,
            target_date=target_date,
            dedupe_key=dedupe_key,
            body=body,
        )
        if created is not None:
            return created

        existing = self.get_by_dedupe_key(dedupe_key)
        if existing is None:
            raise RuntimeError(f"Failed to create or load daily digest notification for dedupe_key={dedupe_key}")
        if existing.status == NotificationStatus.SENT.value and not force:
            return None
        return self._reuse_existing(
            existing,
            notification_type=notification_type,
            channel=channel,
            destination=destination,
            target_date=target_date,
            dedupe_key=dedupe_key,
            body=body,
        )

    def _try_create_pending(
        self,
        *,
        notification_type: str,
        channel: str,
        destination: str,
        target_date: date,
        dedupe_key: str,
        body: str,
    ) -> DailyDigestNotification | None:
        notification = DailyDigestNotification(
            notification_type=notification_type,
            channel=channel,
            destination=destination,
            target_date=target_date,
            dedupe_key=dedupe_key,
            body=body,
            status=NotificationStatus.PENDING.value,
            message_count=0,
        )
        try:
            with self.session.begin_nested():
                self.session.add(notification)
                self.session.flush()
        except IntegrityError:
            return None
        self.session.add(notification)
        self.session.flush()
        return notification

    def _reuse_existing(
        self,
        notification: DailyDigestNotification,
        *,
        notification_type: str,
        channel: str,
        destination: str,
        target_date: date,
        dedupe_key: str,
        body: str,
    ) -> DailyDigestNotification:
        notification.notification_type = notification_type
        notification.channel = channel
        notification.destination = destination
        notification.target_date = target_date
        notification.dedupe_key = dedupe_key
        notification.body = body
        notification.status = NotificationStatus.PENDING.value
        notification.message_count = 0
        notification.external_message_id = None
        notification.error_message = None
        notification.sent_at = None
        self.session.add(notification)
        self.session.flush()
        return notification

    def mark_sent(self, notification: DailyDigestNotification, *, external_message_id: str | None, message_count: int) -> None:
        notification.status = NotificationStatus.SENT.value
        notification.external_message_id = external_message_id
        notification.message_count = message_count
        notification.error_message = None
        notification.sent_at = datetime.now(UTC)
        self.session.add(notification)
        self.session.flush()

    def mark_failed(self, notification: DailyDigestNotification, *, error_message: str, message_count: int) -> None:
        notification.status = NotificationStatus.FAILED.value
        notification.error_message = error_message
        notification.message_count = message_count
        self.session.add(notification)
        self.session.flush()
