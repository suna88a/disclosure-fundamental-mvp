from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import NotificationChannel, NotificationType
from app.repositories.notification_repository import NotificationRepository
from app.services.notification_message_builder import build_dedupe_key, build_notification_body
from app.services.notifiers import DiscordNotifier, DummyNotifier, TelegramNotifier



def dispatch_notifications(session: Session) -> dict[str, int]:
    settings = get_settings()
    channel = NotificationChannel(settings.notification_channel)
    destination = _resolve_destination(
        channel,
        settings.notification_destination,
        settings.telegram_chat_id,
    )
    notifier = _build_notifier(channel)
    repository = NotificationRepository(session)

    analyses = list(
        session.scalars(
            select(AnalysisResult)
            .join(AnalysisResult.disclosure)
            .join(Disclosure.company)
            .options(
                selectinload(AnalysisResult.disclosure).selectinload(Disclosure.company),
                selectinload(AnalysisResult.disclosure).selectinload(Disclosure.valuation_views),
            )
            .where(
                Company.is_active.is_(True),
                AnalysisResult.should_notify.is_(True),
            )
        )
    )

    processed = 0
    sent = 0
    skipped = 0
    failed = 0

    for analysis in analyses:
        processed += 1
        disclosure = analysis.disclosure
        valuation = disclosure.valuation_views[0] if disclosure.valuation_views else None
        dedupe_key = build_dedupe_key(
            disclosure_id=disclosure.id,
            notification_type=NotificationType.ANALYSIS_ALERT.value,
            channel=channel.value,
            destination=destination,
        )
        if repository.get_by_dedupe_key(dedupe_key) is not None:
            skipped += 1
            continue

        body = build_notification_body(
            disclosure=disclosure,
            analysis=analysis,
            valuation=valuation,
            web_base_url=settings.web_base_url,
        )
        notification = repository.create_pending(
            disclosure_id=disclosure.id,
            notification_type=NotificationType.ANALYSIS_ALERT,
            channel=channel,
            destination=destination,
            dedupe_key=dedupe_key,
            body=body,
        )
        try:
            result = notifier.send(destination, body)
            repository.mark_sent(notification, result.external_message_id)
            sent += 1
        except Exception as exc:
            repository.mark_failed(notification, str(exc))
            failed += 1

    session.flush()
    session.expire_all()
    return {"processed": processed, "sent": sent, "skipped": skipped, "failed": failed}



def _build_notifier(channel: NotificationChannel):
    if channel == NotificationChannel.DUMMY:
        return DummyNotifier()
    if channel == NotificationChannel.TELEGRAM:
        return TelegramNotifier()
    if channel == NotificationChannel.DISCORD:
        return DiscordNotifier()
    raise ValueError(f"Unsupported notification channel: {channel}")



def _resolve_destination(
    channel: NotificationChannel,
    configured_destination: str,
    telegram_chat_id: str | None,
) -> str:
    if channel == NotificationChannel.TELEGRAM:
        return telegram_chat_id or configured_destination
    if channel == NotificationChannel.DISCORD:
        return configured_destination or "discord-webhook"
    return configured_destination
