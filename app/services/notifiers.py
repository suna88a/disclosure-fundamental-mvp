from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib import request

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationSendResult:
    external_message_id: str | None


class DummyNotifier:
    def send(self, destination: str, body: str) -> NotificationSendResult:
        return NotificationSendResult(external_message_id=f"dummy:{destination}:{len(body)}")

    def send_payload(self, destination: str, payload: dict[str, object]) -> NotificationSendResult:
        body = json.dumps(payload, ensure_ascii=False)
        return NotificationSendResult(external_message_id=f"dummy:{destination}:{len(body)}")


class TelegramNotifier:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required for telegram notifications.")
        self.bot_token = settings.telegram_bot_token

    def send(self, destination: str, body: str) -> NotificationSendResult:
        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = json.dumps({"chat_id": destination, "text": body}).encode("utf-8")
        req = request.Request(
            api_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=30) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        if not parsed.get("ok"):
            raise ValueError(f"Telegram API returned error: {parsed}")
        result = parsed.get("result", {})
        return NotificationSendResult(external_message_id=str(result.get("message_id")))


class DiscordNotifier:
    def __init__(self, webhook_url: str | None = None) -> None:
        settings = get_settings()
        self.webhook_url = webhook_url or settings.discord_webhook_url
        if not self.webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL is required for discord notifications.")

    def send(self, destination: str, body: str) -> NotificationSendResult:
        return self.send_payload(destination, {"content": body})

    def send_payload(self, destination: str, payload: dict[str, object]) -> NotificationSendResult:
        payload_summary = summarize_discord_payload(payload)
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            logger.exception("Discord webhook request failed payload=%s", payload_summary)
            raise ValueError(f"Discord webhook request failed payload={payload_summary}: {exc}") from exc

        if response.status_code >= 400:
            response_text = _truncate_text(response.text, 1500)
            logger.error(
                "Discord webhook HTTP error status=%s payload=%s body=%s",
                response.status_code,
                payload_summary,
                response_text,
            )
            raise ValueError(
                f"Discord webhook HTTP {response.status_code} payload={payload_summary} body={response_text}"
            )

        response.raise_for_status()
        message_id = response.headers.get("X-Discord-Message-Id") or None
        return NotificationSendResult(external_message_id=message_id)


def summarize_discord_payload(payload: dict[str, object]) -> str:
    content = payload.get("content") if isinstance(payload, dict) else None
    embeds = payload.get("embeds") if isinstance(payload, dict) else None
    embed_list = embeds if isinstance(embeds, list) else []

    title_lengths: list[int] = []
    description_lengths: list[int] = []
    total_embed_chars = 0
    for embed in embed_list:
        if not isinstance(embed, dict):
            continue
        title = str(embed.get("title") or "")
        description = str(embed.get("description") or "")
        title_lengths.append(len(title))
        description_lengths.append(len(description))
        total_embed_chars += len(title) + len(description)

    payload_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return (
        f"content_len={len(str(content or ''))} embeds={len(embed_list)} "
        f"title_lens={title_lengths[:10]} desc_lens={description_lengths[:10]} "
        f"total_embed_chars={total_embed_chars} payload_bytes={payload_bytes}"
    )


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"
