from __future__ import annotations

import requests

from app.services.notifiers import DiscordNotifier, summarize_discord_payload


class DummyResponse:
    def __init__(self, status_code: int, text: str = "", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def test_summarize_discord_payload_reports_embed_lengths() -> None:
    payload = {
        "content": "hello",
        "embeds": [
            {"title": "summary", "description": "abc"},
            {"title": "category", "description": "defgh"},
        ],
    }

    summary = summarize_discord_payload(payload)

    assert "content_len=5" in summary
    assert "embeds=2" in summary
    assert "title_lens=[7, 8]" in summary
    assert "desc_lens=[3, 5]" in summary


def test_discord_notifier_send_payload_includes_response_body_on_http_error(monkeypatch) -> None:
    def fake_post(url, json, timeout):
        return DummyResponse(400, '{"message": "Invalid Form Body", "embeds": ["0"]}')

    monkeypatch.setattr("app.services.notifiers.requests.post", fake_post)

    notifier = DiscordNotifier(webhook_url="https://discord.example/webhook")

    try:
        notifier.send_payload("discord-raw", {"content": "hello"})
    except ValueError as exc:
        message = str(exc)
        assert "HTTP 400" in message
        assert "Invalid Form Body" in message
        assert "content_len=5" in message
    else:
        raise AssertionError("Expected ValueError for Discord 400 response")
