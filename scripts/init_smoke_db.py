from __future__ import annotations

from sqlalchemy import inspect, text

from app.db import engine, init_db
from app.models.daily_digest_notification import DailyDigestNotification
from app.models.price_daily import PriceDaily


def ensure_job_runs_result_summary_json_column() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("job_runs"):
        raise RuntimeError("job_runs table does not exist. Run init_db first.")
    columns = {column["name"] for column in inspector.get_columns("job_runs")}
    if "result_summary_json" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE job_runs ADD COLUMN result_summary_json TEXT"))


def main() -> None:
    init_db()
    ensure_job_runs_result_summary_json_column()
    PriceDaily.__table__.create(bind=engine, checkfirst=True)
    DailyDigestNotification.__table__.create(bind=engine, checkfirst=True)
    print("Smoke DB initialized.")


if __name__ == "__main__":
    main()
