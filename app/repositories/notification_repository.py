from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import NotificationChannel, NotificationStatus, NotificationType
from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_dedupe_key(self, dedupe_key: str) -> Notification | None:
        return self.session.scalar(select(Notification).where(Notification.dedupe_key == dedupe_key))

    def create_pending(
        self,
        *,
        disclosure_id: int,
        notification_type: NotificationType,
        channel: NotificationChannel,
        destination: str,
        dedupe_key: str,
        body: str,
    ) -> Notification:
        notification = Notification(
            disclosure_id=disclosure_id,
            notification_type=notification_type,
            channel=channel,
            destination=destination,
            dedupe_key=dedupe_key,
            body=body,
            status=NotificationStatus.PENDING,
        )
        self.session.add(notification)
        self.session.flush()
        return notification

    def mark_sent(self, notification: Notification, external_message_id: str | None) -> None:
        notification.status = NotificationStatus.SENT
        notification.external_message_id = external_message_id
        notification.error_message = None
        notification.sent_at = datetime.now(UTC)
        self.session.add(notification)
        self.session.flush()

    def mark_failed(self, notification: Notification, error_message: str) -> None:
        notification.status = NotificationStatus.FAILED
        notification.error_message = error_message
        self.session.add(notification)
        self.session.flush()
