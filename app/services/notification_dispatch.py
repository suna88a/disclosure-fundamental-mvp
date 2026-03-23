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
from app.models.enums import DisclosureCategory, NotificationChannel, NotificationType
from app.repositories.daily_digest_notification_repository import DailyDigestNotificationRepository
from app.repositories.notification_repository import NotificationRepository
from app.services.notification_message_builder import (
    build_dedupe_key,
    build_empty_raw_digest_body,
    build_empty_raw_digest_discord_payload,
    build_notification_body,
    build_raw_disclosure_batches,
    build_raw_discord_batches,
    build_structured_notification_body,
    filter_raw_disclosures,
)
from app.services.notifiers import DiscordNotifier, DummyNotifier, TelegramNotifier
from app.services.analysis_alert_valuation_bridge_service import build_analysis_alert_valuation_draft
from app.services.guidance_revision_notification_service import build_guidance_revision_notification_text
from app.services.dividend_revision_notification_service import build_dividend_revision_notification_text


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

        revision_body: str | None = None
        if settings.analysis_alert_enable_revision_bodies:
            revision_preview = _build_revision_notification_preview(session, disclosure)
            if revision_preview is not None:
                if settings.analysis_alert_revision_body_dry_run:
                    logger.info(
                        "analysis_alert_revision_body_dry_run disclosure_id=%s headline=%s metadata=%s body_lines=%s",
                        disclosure.id,
                        revision_preview.headline,
                        revision_preview.metadata,
                        revision_preview.body_lines,
                    )
                else:
                    detail_url = f"{settings.web_base_url.rstrip('/')}/disclosures/{disclosure.id}"
                    revision_body = build_structured_notification_body(
                        headline=revision_preview.headline,
                        body_lines=revision_preview.body_lines,
                        detail_url=detail_url,
                    )

        if revision_body is not None:
            body = revision_body
        else:
            valuation_lines: tuple[str, ...] = ()
            if settings.analysis_alert_enable_valuation_lines:
                valuation_draft = build_analysis_alert_valuation_draft(session, disclosure)
                if valuation_draft is not None:
                    if settings.analysis_alert_valuation_dry_run:
                        logger.info(
                            "analysis_alert_valuation_dry_run disclosure_id=%s title=%s shown_fields=%s omitted_fields=%s suppressed_reasons=%s warnings=%s",
                            disclosure.id,
                            valuation_draft.title,
                            valuation_draft.metadata.get("shown_fields"),
                            valuation_draft.metadata.get("omitted_fields"),
                            valuation_draft.metadata.get("suppressed_reasons"),
                            valuation_draft.metadata.get("warnings"),
                        )
                    elif valuation_draft.valuation_lines:
                        valuation_lines = valuation_draft.valuation_lines

            body = build_notification_body(
                disclosure=disclosure,
                analysis=analysis,
                valuation=valuation,
                web_base_url=settings.web_base_url,
                valuation_lines=valuation_lines,
            )
        notification = repository.create_pending(
            disclosure_id=disclosure.id,
            notification_type=NotificationType.ANALYSIS_ALERT.value,
            channel=channel.value,
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
) -> dict[str, int | str | None]:
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

    return _dispatch_batched_market_notifications(
        session=session,
        disclosures=disclosures,
        filtered_out=filtered_out,
        channel=channel,
        destination=destination,
        notifier=notifier,
        repository=repository,
        notification_type=NotificationType.RAW_DISCLOSURE_BATCH.value,
        batch_size=settings.raw_notification_batch_size,
        mode=mode,
        target_date=target_date,
        lookback_minutes=effective_lookback_minutes,
        force=force,
        dry_run=dry_run,
    )


def dispatch_daily_raw_digest_notifications(
    session: Session,
    *,
    target_date: date | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, int | str | None]:
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
        raise ValueError("RAW_DISCORD_WEBHOOK_URL is required for daily raw digest discord notifications.")
    notifier = _build_notifier(channel, discord_webhook_url=settings.raw_discord_webhook_url)
    repository = DailyDigestNotificationRepository(session)

    effective_target_date = target_date or datetime.now(JST).date()
    all_candidates = _select_daily_raw_digest_candidates(session, target_date=effective_target_date)
    disclosures = filter_raw_disclosures(all_candidates)
    filtered_out = len(all_candidates) - len(disclosures)
    dedupe_key = _build_daily_digest_dedupe_key(
        notification_type=NotificationType.DAILY_RAW_DIGEST.value,
        channel=channel.value,
        destination=destination,
        target_date=effective_target_date,
    )

    if disclosures:
        discord_batches = build_raw_discord_batches(
            disclosures=disclosures,
            filtered_out_count=filtered_out,
            batch_size=settings.raw_notification_batch_size,
        )
        text_batches = build_raw_disclosure_batches(
            disclosures=disclosures,
            batch_size=settings.raw_notification_batch_size,
        )
        body_summary = f"daily_raw_digest target_date={effective_target_date.isoformat()} eligible={len(disclosures)} filtered_out={filtered_out}"
        messages_planned = len(discord_batches) if channel == NotificationChannel.DISCORD else len(text_batches)
        empty_digest = False
        empty_digest_planned = False
    else:
        body_summary = build_empty_raw_digest_body(target_date=effective_target_date)
        messages_planned = 1
        empty_digest = True
        empty_digest_planned = True

    if dry_run:
        result = _notification_result(
            mode="daily_digest",
            target_date=effective_target_date,
            lookback_minutes=None,
            processed=len(all_candidates),
            filtered_out=filtered_out,
            candidates=len(disclosures),
            skipped=0,
            sent=0,
            failed=0,
            messages_sent=0,
            forced=force,
            dry_run=True,
            batch_count=messages_planned,
            batched_disclosures=len(disclosures),
            empty_digest=int(empty_digest),
            empty_digest_sent=0,
            empty_digest_planned=int(empty_digest_planned),
        )
        _log_notification_result(NotificationType.DAILY_RAW_DIGEST.value, result)
        return result

    digest_notification = repository.prepare_pending(
        notification_type=NotificationType.DAILY_RAW_DIGEST.value,
        channel=channel.value,
        destination=destination,
        target_date=effective_target_date,
        dedupe_key=dedupe_key,
        body=body_summary,
        force=force,
    )
    if digest_notification is None:
        result = _notification_result(
            mode="daily_digest",
            target_date=effective_target_date,
            lookback_minutes=None,
            processed=len(all_candidates),
            filtered_out=filtered_out,
            candidates=len(disclosures),
            skipped=1,
            sent=0,
            failed=0,
            messages_sent=0,
            forced=force,
            dry_run=False,
            empty_digest=int(empty_digest),
            empty_digest_sent=0,
            empty_digest_planned=0,
        )
        _log_notification_result(NotificationType.DAILY_RAW_DIGEST.value, result)
        return result

    messages_sent = 0
    sent = 0
    failed = 0
    last_external_message_id: str | None = None

    try:
        if disclosures:
            if channel == NotificationChannel.DISCORD:
                for batch in discord_batches:
                    send_result = notifier.send_payload(destination, batch.payload)
                    messages_sent += 1
                    sent += len(batch.disclosures)
                    last_external_message_id = send_result.external_message_id or last_external_message_id
            else:
                for disclosures_in_batch, body in text_batches:
                    send_result = notifier.send(destination, body)
                    messages_sent += 1
                    sent += len(disclosures_in_batch)
                    last_external_message_id = send_result.external_message_id or last_external_message_id
        else:
            if channel == NotificationChannel.DISCORD:
                empty_payload = build_empty_raw_digest_discord_payload(target_date=effective_target_date)
                send_result = notifier.send_payload(destination, empty_payload)
            else:
                send_result = notifier.send(destination, body_summary)
            messages_sent = 1
            last_external_message_id = send_result.external_message_id

        repository.mark_sent(
            digest_notification,
            external_message_id=last_external_message_id,
            message_count=messages_sent,
        )
    except Exception as exc:
        repository.mark_failed(
            digest_notification,
            error_message=str(exc),
            message_count=messages_sent,
        )
        failed = len(disclosures) if disclosures else 1
        result = _notification_result(
            mode="daily_digest",
            target_date=effective_target_date,
            lookback_minutes=None,
            processed=len(all_candidates),
            filtered_out=filtered_out,
            candidates=len(disclosures),
            skipped=0,
            sent=sent,
            failed=failed,
            messages_sent=messages_sent,
            forced=force,
            dry_run=False,
            empty_digest=int(empty_digest),
            empty_digest_sent=0,
            empty_digest_planned=0,
        )
        _log_notification_result(NotificationType.DAILY_RAW_DIGEST.value, result)
        session.flush()
        session.expire_all()
        return result

    session.flush()
    session.expire_all()
    result = _notification_result(
        mode="daily_digest",
        target_date=effective_target_date,
        lookback_minutes=None,
        processed=len(all_candidates),
        filtered_out=filtered_out,
        candidates=len(disclosures),
        skipped=0,
        sent=sent,
        failed=0,
        messages_sent=messages_sent,
        forced=force,
        dry_run=False,
        empty_digest=int(empty_digest),
        empty_digest_sent=int(empty_digest),
        empty_digest_planned=0,
    )
    _log_notification_result(NotificationType.DAILY_RAW_DIGEST.value, result)
    return result


def _dispatch_batched_market_notifications(
    *,
    session: Session,
    disclosures: list[Disclosure],
    filtered_out: int,
    channel: NotificationChannel,
    destination: str,
    notifier,
    repository: NotificationRepository,
    notification_type: str,
    batch_size: int,
    mode: str,
    target_date: date | None,
    lookback_minutes: int | None,
    force: bool,
    dry_run: bool,
) -> dict[str, int | str | None]:
    processed = len(disclosures)
    skipped = 0
    sent = 0
    failed = 0
    pending_disclosures: list[Disclosure] = []

    for disclosure in disclosures:
        dedupe_key = build_dedupe_key(
            disclosure_id=disclosure.id,
            notification_type=notification_type,
            channel=channel.value,
            destination=destination,
        )
        if not force and repository.get_by_dedupe_key(dedupe_key) is not None:
            skipped += 1
            continue
        pending_disclosures.append(disclosure)

    if not pending_disclosures:
        result = _notification_result(
            mode=mode,
            target_date=target_date,
            lookback_minutes=lookback_minutes,
            processed=processed,
            filtered_out=filtered_out,
            candidates=0,
            skipped=skipped,
            sent=0,
            failed=0,
            messages_sent=0,
            forced=force,
            dry_run=dry_run,
        )
        _log_notification_result(notification_type, result)
        return result

    if channel == NotificationChannel.DISCORD:
        discord_batches = build_raw_discord_batches(
            disclosures=pending_disclosures,
            filtered_out_count=filtered_out,
            batch_size=batch_size,
        )
        candidate_count = sum(len(batch.disclosures) for batch in discord_batches)
        batch_count = len(discord_batches)
        if dry_run:
            result = _notification_result(
                mode=mode,
                target_date=target_date,
                lookback_minutes=lookback_minutes,
                processed=processed,
                filtered_out=filtered_out,
                candidates=candidate_count,
                skipped=skipped,
                sent=0,
                failed=0,
                messages_sent=0,
                forced=force,
                dry_run=True,
                batch_count=batch_count,
                batched_disclosures=candidate_count,
            )
            _log_notification_result(notification_type, result)
            return result

        messages_sent = 0
        for batch in discord_batches:
            notifications = []
            persist_notifications = not force
            for disclosure in batch.disclosures:
                if not persist_notifications:
                    continue
                dedupe_key = build_dedupe_key(
                    disclosure_id=disclosure.id,
                    notification_type=notification_type,
                    channel=channel.value,
                    destination=destination,
                )
                notifications.append(
                    repository.create_pending(
                        disclosure_id=disclosure.id,
                        notification_type=notification_type,
                        channel=channel.value,
                        destination=destination,
                        dedupe_key=dedupe_key,
                        body="raw-discord-embed",
                    )
                )
            try:
                result = notifier.send_payload(destination, batch.payload)
                messages_sent += 1
                if notifications:
                    for notification in notifications:
                        repository.mark_sent(notification, result.external_message_id)
                        sent += 1
                else:
                    sent += len(batch.disclosures)
            except Exception as exc:
                if notifications:
                    for notification in notifications:
                        repository.mark_failed(notification, str(exc))
                        failed += 1
                else:
                    failed += len(batch.disclosures)
    else:
        batches = build_raw_disclosure_batches(
            disclosures=pending_disclosures,
            batch_size=batch_size,
        )
        candidate_count = sum(len(disclosures_in_batch) for disclosures_in_batch, _ in batches)
        batch_count = len(batches)
        if dry_run:
            result = _notification_result(
                mode=mode,
                target_date=target_date,
                lookback_minutes=lookback_minutes,
                processed=processed,
                filtered_out=filtered_out,
                candidates=candidate_count,
                skipped=skipped,
                sent=0,
                failed=0,
                messages_sent=0,
                forced=force,
                dry_run=True,
                batch_count=batch_count,
                batched_disclosures=candidate_count,
            )
            _log_notification_result(notification_type, result)
            return result

        force_note = "\n\n[FORCED REPLAY]" if force else ""
        messages_sent = 0
        for disclosures_in_batch, body in batches:
            notifications = []
            persist_notifications = not force
            for disclosure in disclosures_in_batch:
                if not persist_notifications:
                    continue
                dedupe_key = build_dedupe_key(
                    disclosure_id=disclosure.id,
                    notification_type=notification_type,
                    channel=channel.value,
                    destination=destination,
                )
                notifications.append(
                    repository.create_pending(
                        disclosure_id=disclosure.id,
                        notification_type=notification_type,
                        channel=channel.value,
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
    result = _notification_result(
        mode=mode,
        target_date=target_date,
        lookback_minutes=lookback_minutes,
        processed=processed,
        filtered_out=filtered_out,
        candidates=len(pending_disclosures),
        skipped=skipped,
        sent=sent,
        failed=failed,
        messages_sent=messages_sent,
        forced=force,
        dry_run=False,
    )
    _log_notification_result(notification_type, result)
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


def _select_daily_raw_digest_candidates(
    session: Session,
    *,
    target_date: date,
) -> list[Disclosure]:
    start_at = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=JST)
    cutoff_at = datetime(target_date.year, target_date.month, target_date.day, 17, 0, 0, tzinfo=JST)
    query = (
        select(Disclosure)
        .options(selectinload(Disclosure.company))
        .where(Disclosure.disclosed_at >= start_at, Disclosure.disclosed_at <= cutoff_at)
        .order_by(Disclosure.disclosed_at.desc(), Disclosure.id.desc())
    )
    return list(session.scalars(query))


def _build_daily_digest_dedupe_key(
    *,
    notification_type: str,
    channel: str,
    destination: str,
    target_date: date,
) -> str:
    return f"{notification_type}:{target_date.isoformat()}:{channel}:{destination}"


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


def _notification_result(
    *,
    mode: str,
    target_date: date | None,
    lookback_minutes: int | None,
    processed: int,
    filtered_out: int,
    candidates: int,
    skipped: int,
    sent: int,
    failed: int,
    messages_sent: int,
    forced: bool,
    dry_run: bool,
    batch_count: int | None = None,
    batched_disclosures: int | None = None,
    empty_digest: int | None = None,
    empty_digest_sent: int | None = None,
    empty_digest_planned: int | None = None,
) -> dict[str, int | str | None]:
    result: dict[str, int | str | None] = {
        "mode": mode,
        "target_date": target_date.isoformat() if target_date else None,
        "lookback_minutes": lookback_minutes,
        "processed": processed,
        "filtered_out": filtered_out,
        "candidates": candidates,
        "skipped": skipped,
        "sent": sent,
        "failed": failed,
        "messages_sent": messages_sent,
        "forced": int(forced),
        "dry_run": int(dry_run),
    }
    if batch_count is not None:
        result["batch_count"] = batch_count
    if batched_disclosures is not None:
        result["batched_disclosures"] = batched_disclosures
    if empty_digest is not None:
        result["empty_digest"] = empty_digest
    if empty_digest_sent is not None:
        result["empty_digest_sent"] = empty_digest_sent
    if empty_digest_planned is not None:
        result["empty_digest_planned"] = empty_digest_planned
    return result


def _log_notification_result(notification_type: str, result: dict[str, int | str | None]) -> None:
    logger.info(
        "%s mode=%s target_date=%s lookback_minutes=%s processed=%s filtered_out=%s candidates=%s skipped=%s sent=%s failed=%s messages_sent=%s forced=%s empty_digest=%s empty_digest_sent=%s empty_digest_planned=%s",
        notification_type,
        result.get("mode"),
        result.get("target_date"),
        result.get("lookback_minutes"),
        result.get("processed"),
        result.get("filtered_out"),
        result.get("candidates"),
        result.get("skipped"),
        result.get("sent"),
        result.get("failed"),
        result.get("messages_sent"),
        result.get("forced"),
        result.get("empty_digest"),
        result.get("empty_digest_sent"),
        result.get("empty_digest_planned"),
    )



def _build_revision_notification_preview(session: Session, disclosure: Disclosure):
    if disclosure.category == DisclosureCategory.GUIDANCE_REVISION:
        return build_guidance_revision_notification_text(session, disclosure)
    if disclosure.category == DisclosureCategory.DIVIDEND_REVISION:
        return build_dividend_revision_notification_text(session, disclosure)
    return None
