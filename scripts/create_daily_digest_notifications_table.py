from app.db import engine
from app.models.daily_digest_notification import DailyDigestNotification


def main() -> None:
    DailyDigestNotification.__table__.create(bind=engine, checkfirst=True)
    print("daily_digest_notifications table ensured.")


if __name__ == "__main__":
    main()
