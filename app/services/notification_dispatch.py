from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import NotificationChannel, NotificationType
from app.repositories.notification_repository import NotificationRepository
from app.services.notification_message_builder import (
    build_dedupe_key,
    build_notification_body,
    build_raw_disclosure_batches,
    filter_raw_disclosures,
)
from app.services.notifiers import DiscordNotifier, DummyNotifier, TelegramNotifier


JST = ZoneInfo("Asia/Tokyo")
logger = logging.getLogger(__name__)



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



def dispatch_raw_disclosure_notifications(
    session: Session,
    *,
    lookback_minutes: int | None = None,
    target_date: date | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    settings = get_settings()
    if not settings.raw_notification_channel:
        return {"processed": 0, "sent": 0, "skipped": 0, "failed": 0, "messages_sent": 0, "disabled": 1}

    channel = NotificationChannel(settings.raw_notification_channel)
    destination = _resolve_destination(
        channel,
        settings.raw_notification_destination,
        settings.telegram_chat_id,
    )
    if channel == NotificationChannel.DISCORD and not settings.raw_discord_webhook_url:
        raise ValueError("RAW_DISCORD_WEBHOOK_URL is required for raw discord notifications.")
    notifier = _build_notifier(channel, discord_webhook_url=settings.raw_discord_webhook_url)
    repository = NotificationRepository(session)

    if force and target_date is None:
        raise ValueError("--force requires --date for raw disclosure notifications.")

    effective_lookback_minutes = lookback_minutes or settings.raw_notification_lookback_minutes
    mode = "replay" if target_date is not None else "lookback"
    all_candidates = _select_raw_disclosure_candidates(
        session,
        lookback_minutes=effective_lookback_minutes,
        target_date=target_date,
    )
    disclosures = filter_raw_disclosures(all_candidates)
    filtered_out = len(all_candidates) - len(disclosures)

    processed = 0
    skipped = 0
    sent = 0
    failed = 0
    pending_disclosures: list[Disclosure] = []

    for disclosure in disclosures:
        processed += 1
        dedupe_key = build_dedupe_key(
            disclosure_id=disclosure.id,
            notification_type=NotificationType.RAW_DISCLOSURE_BATCH.value,
            channel=channel.value,
            destination=destination,
        )
        if not force and repository.get_by_dedupe_key(dedupe_key) is not None:
            skipped += 1
            continue
        pending_disclosures.append(disclosure)

    if not pending_disclosures:
        result = {
            "mode": mode,
            "target_date": target_date.isoformat() if target_date else None,
            "lookback_minutes": effective_lookback_minutes,
            "processed": processed,
            "filtered_out": filtered_out,
            "candidates": 0,
            "skipped": skipped,
            "sent": 0,
            "failed": 0,
            "messages_sent": 0,
            "forced": int(force),
            "dry_run": int(dry_run),
        }
        logger.info("raw_notification mode=%s target_date=%s lookback_minutes=%s processed=%s filtered_out=%s candidates=%s skipped=%s sent=%s messages_sent=%s forced=%s", mode, result["target_date"], effective_lookback_minutes, processed, filtered_out, 0, skipped, 0, 0, int(force))
        return result

    batches = build_raw_disclosure_batches(
        disclosures=pending_disclosures,
        batch_size=settings.raw_notification_batch_size,
    )
    messages_sent = 0
    candidate_count = sum(len(disclosures_in_batch) for disclosures_in_batch, _ in batches)

    if dry_run:
        result = {
            "mode": mode,
            "target_date": target_date.isoformat() if target_date else None,
            "lookback_minutes": effective_lookback_minutes,
            "processed": processed,
            "filtered_out": filtered_out,
            "candidates": candidate_count,
            "skipped": skipped,
            "sent": 0,
            "failed": 0,
            "messages_sent": 0,
            "forced": int(force),
            "dry_run": 1,
            "batch_count": len(batches),
            "batched_disclosures": candidate_count,
        }
        logger.info("raw_notification mode=%s target_date=%s lookback_minutes=%s processed=%s filtered_out=%s candidates=%s skipped=%s sent=%s messages_sent=%s forced=%s", mode, result["target_date"], effective_lookback_minutes, processed, filtered_out, candidate_count, skipped, 0, 0, int(force))
        return result

    force_note = "\n\n[FORCED REPLAY]" if force else ""
    for disclosures_in_batch, body in batches:
        notifications = []
        persist_notifications = not force
        for disclosure in disclosures_in_batch:
            if not persist_notifications:
                continue
            dedupe_key = build_dedupe_key(
                disclosure_id=disclosure.id,
                notification_type=NotificationType.RAW_DISCLOSURE_BATCH.value,
                channel=channel.value,
                destination=destination,
            )
            notifications.append(
                repository.create_pending(
                    disclosure_id=disclosure.id,
                    notification_type=NotificationType.RAW_DISCLOSURE_BATCH,
                    channel=channel,
                    destination=destination,
                    dedupe_key=dedupe_key,
                    body=body,
                )
            )
        try:
            result = notifier.send(destination, body + force_note)
            messages_sent += 1
            if notifications:
                for notification in notifications:
                    repository.mark_sent(notification, result.external_message_id)
                    sent += 1
            else:
                sent += len(disclosures_in_batch)
        except Exception as exc:
            if notifications:
                for notification in notifications:
                    repository.mark_failed(notification, str(exc))
                    failed += 1
            else:
                failed += len(disclosures_in_batch)

    session.flush()
    session.expire_all()
    result = {
        "mode": mode,
        "target_date": target_date.isoformat() if target_date else None,
        "lookback_minutes": effective_lookback_minutes,
        "processed": processed,
        "filtered_out": filtered_out,
        "candidates": candidate_count,
        "skipped": skipped,
        "sent": sent,
        "failed": failed,
        "messages_sent": messages_sent,
        "forced": int(force),
        "dry_run": 0,
    }
    logger.info("raw_notification mode=%s target_date=%s lookback_minutes=%s processed=%s filtered_out=%s candidates=%s skipped=%s sent=%s messages_sent=%s forced=%s", mode, result["target_date"], effective_lookback_minutes, processed, filtered_out, candidate_count, skipped, sent, messages_sent, int(force))
    return result



def _select_raw_disclosure_candidates(
    session: Session,
    *,
    lookback_minutes: int,
    target_date: date | None,
) -> list[Disclosure]:
    query = select(Disclosure).options(selectinload(Disclosure.company))

    if target_date is not None:
        start_at = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=JST)
        end_at = start_at + timedelta(days=1)
        query = query.where(Disclosure.disclosed_at >= start_at, Disclosure.disclosed_at < end_at)
    else:
        cutoff = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
        query = query.where(Disclosure.created_at >= cutoff)

    query = query.order_by(Disclosure.disclosed_at.desc(), Disclosure.id.desc())
    return list(session.scalars(query))



def _build_notifier(channel: NotificationChannel, *, discord_webhook_url: str | None = None):
    if channel == NotificationChannel.DUMMY:
        return DummyNotifier()
    if channel == NotificationChannel.TELEGRAM:
        return TelegramNotifier()
    if channel == NotificationChannel.DISCORD:
        return DiscordNotifier(webhook_url=discord_webhook_url)
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
