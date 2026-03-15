from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import request

from app.config import get_settings


@dataclass(frozen=True)
class NotificationSendResult:
    external_message_id: str | None


class DummyNotifier:
    def send(self, destination: str, body: str) -> NotificationSendResult:
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
