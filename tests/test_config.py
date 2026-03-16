from app.config import get_settings



def test_settings_reads_discord_webhook_url(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "discord")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "discord-room")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.discord_webhook_url == "https://discord.example/webhook"
    assert settings.notification_channel == "discord"
    assert settings.notification_destination == "discord-room"



def test_settings_keeps_existing_telegram_fields(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "telegram-chat")
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "telegram")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "telegram-room")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.telegram_bot_token == "telegram-token"
    assert settings.telegram_chat_id == "telegram-chat"
    assert settings.notification_channel == "telegram"
    assert settings.notification_destination == "telegram-room"
