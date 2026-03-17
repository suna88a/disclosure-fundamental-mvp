from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import request

import requests

from app.config import get_settings


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
        response = requests.post(
            self.webhook_url,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        message_id = response.headers.get("X-Discord-Message-Id") or None
        return NotificationSendResult(external_message_id=message_id)
