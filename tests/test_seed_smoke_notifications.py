from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import Base
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.services.notification_dispatch import dispatch_notifications
from app.services.notifiers import NotificationSendResult
from scripts.init_smoke_db import ensure_job_runs_result_summary_json_column
from scripts.seed_smoke_notifications import seed_smoke_notifications


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def test_seed_smoke_notifications_inserts_minimum_fixture_set() -> None:
    session = _build_session()

    result = seed_smoke_notifications(session)

    assert result == {
        "companies": 4,
        "disclosures": 4,
        "analysis_results": 4,
        "financial_reports": 2,
        "guidance_revisions": 2,
        "dividend_revisions": 2,
        "price_daily": 4,
    }
    assert session.scalar(select(Company).where(Company.code == "9101")) is not None
    assert session.scalar(select(Disclosure).where(Disclosure.source_name == "smoke-seed")) is not None


def test_seed_smoke_notifications_is_idempotent_for_same_session() -> None:
    session = _build_session()

    first = seed_smoke_notifications(session)
    second = seed_smoke_notifications(session)

    assert first == second
    assert len(session.scalars(select(Company).where(Company.code.in_(["9101", "9102", "9103", "9104"]))).all()) == 4
    assert len(session.scalars(select(Disclosure).where(Disclosure.source_name == "smoke-seed")).all()) == 4


def test_seed_smoke_notifications_supports_dispatch_dry_run_mode(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "local-test")
    monkeypatch.setenv("WEB_BASE_URL", "https://example.com/app")
    monkeypatch.setenv("ANALYSIS_ALERT_ENABLE_VALUATION_LINES", "true")
    monkeypatch.setenv("ANALYSIS_ALERT_VALUATION_DRY_RUN", "true")
    get_settings.cache_clear()

    sent_bodies: list[str] = []

    def fake_send(self, destination: str, body: str) -> NotificationSendResult:
        sent_bodies.append(body)
        return NotificationSendResult(external_message_id=f"smoke-dry-{len(sent_bodies)}")

    monkeypatch.setattr("app.services.notification_dispatch.DummyNotifier.send", fake_send)

    session = _build_session()
    seed_smoke_notifications(session)

    result = dispatch_notifications(session)
    notifications = session.scalars(select(Notification).where(Notification.notification_type == NotificationType.ANALYSIS_ALERT)).all()

    assert result["sent"] == 4
    assert len(sent_bodies) == 4
    assert len(notifications) == 4
    combined = "\n".join(sent_bodies)
    assert "PER(会社予想EPS):" not in combined
    assert "配当利回り:" not in combined


def test_seed_smoke_notifications_supports_dispatch_feature_on(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "local-test")
    monkeypatch.setenv("WEB_BASE_URL", "https://example.com/app")
    monkeypatch.setenv("ANALYSIS_ALERT_ENABLE_VALUATION_LINES", "true")
    monkeypatch.setenv("ANALYSIS_ALERT_VALUATION_DRY_RUN", "false")
    get_settings.cache_clear()

    sent_bodies: list[str] = []

    def fake_send(self, destination: str, body: str) -> NotificationSendResult:
        sent_bodies.append(body)
        return NotificationSendResult(external_message_id=f"smoke-on-{len(sent_bodies)}")

    monkeypatch.setattr("app.services.notification_dispatch.DummyNotifier.send", fake_send)

    session = _build_session()
    seed_smoke_notifications(session)

    result = dispatch_notifications(session)

    assert result["sent"] == 4
    body_by_code = {}
    for body in sent_bodies:
        code = body.splitlines()[0].split()[0]
        body_by_code[code] = body

    assert "PER(会社予想EPS): 20.0" in body_by_code["9101"]
    assert "配当利回り: 2.0%" in body_by_code["9102"]
    assert "PER(会社予想EPS):" not in body_by_code["9103"]
    assert "配当利回り:" not in body_by_code["9104"]


def test_ensure_job_runs_result_summary_json_column_adds_missing_column(monkeypatch) -> None:
    db_path = Path("data/test_job_runs_column_smoke.db")
    if db_path.exists():
        db_path.unlink()
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE job_runs (id INTEGER PRIMARY KEY, job_name TEXT NOT NULL)")

    import scripts.init_smoke_db as init_smoke_db

    monkeypatch.setattr(init_smoke_db, "engine", engine)
    init_smoke_db.ensure_job_runs_result_summary_json_column()

    columns = {column["name"] for column in inspect(engine).get_columns("job_runs")}
    assert "result_summary_json" in columns
    engine.dispose()
    if db_path.exists():
        db_path.unlink()


def test_seed_smoke_notifications_revision_body_feature_off_keeps_existing_body(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "local-test")
    monkeypatch.setenv("WEB_BASE_URL", "https://example.com/app")
    monkeypatch.setenv("ANALYSIS_ALERT_ENABLE_REVISION_BODIES", "false")
    get_settings.cache_clear()

    sent_bodies: list[str] = []

    def fake_send(self, destination: str, body: str) -> NotificationSendResult:
        sent_bodies.append(body)
        return NotificationSendResult(external_message_id=f"revision-off-{len(sent_bodies)}")

    monkeypatch.setattr("app.services.notification_dispatch.DummyNotifier.send", fake_send)

    session = _build_session()
    seed_smoke_notifications(session)

    result = dispatch_notifications(session)

    assert result["sent"] == 4
    combined = "\n".join(sent_bodies)
    assert "[業績修正]" not in combined
    assert "売上高:" not in combined
    assert "中間配当:" not in combined


def test_seed_smoke_notifications_revision_body_feature_on_uses_guidance_and_dividend_bodies(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "local-test")
    monkeypatch.setenv("WEB_BASE_URL", "https://example.com/app")
    monkeypatch.setenv("ANALYSIS_ALERT_ENABLE_REVISION_BODIES", "true")
    monkeypatch.setenv("ANALYSIS_ALERT_REVISION_BODY_DRY_RUN", "false")
    get_settings.cache_clear()

    sent_bodies: list[str] = []

    def fake_send(self, destination: str, body: str) -> NotificationSendResult:
        sent_bodies.append(body)
        return NotificationSendResult(external_message_id=f"revision-on-{len(sent_bodies)}")

    monkeypatch.setattr("app.services.notification_dispatch.DummyNotifier.send", fake_send)

    session = _build_session()
    seed_smoke_notifications(session)

    result = dispatch_notifications(session)

    assert result["sent"] == 4
    body_by_code = {body.splitlines()[0].split()[1]: body for body in sent_bodies}
    assert body_by_code["9101"].splitlines()[0] == "[業績修正] 9101 スモーク業績予想"
    assert "売上高: 10,000 -> 10,800" in body_by_code["9101"]
    assert "PER(会社予想EPS): 20.0" in body_by_code["9101"]
    assert body_by_code["9102"].splitlines()[0] == "[配当修正] 9102 スモーク配当修正"
    assert "年間配当: 50.0 -> 60.0" in body_by_code["9102"]
    assert "配当利回り: 2.0%" in body_by_code["9102"]
    assert "PER(会社予想EPS):" not in body_by_code["9103"]
    assert "配当利回り:" not in body_by_code["9104"]


def test_seed_smoke_notifications_revision_body_dry_run_keeps_existing_body(monkeypatch, caplog) -> None:
    caplog.set_level("INFO")
    monkeypatch.setenv("NOTIFICATION_CHANNEL", "dummy")
    monkeypatch.setenv("NOTIFICATION_DESTINATION", "local-test")
    monkeypatch.setenv("WEB_BASE_URL", "https://example.com/app")
    monkeypatch.setenv("ANALYSIS_ALERT_ENABLE_REVISION_BODIES", "true")
    monkeypatch.setenv("ANALYSIS_ALERT_REVISION_BODY_DRY_RUN", "true")
    get_settings.cache_clear()

    sent_bodies: list[str] = []

    def fake_send(self, destination: str, body: str) -> NotificationSendResult:
        sent_bodies.append(body)
        return NotificationSendResult(external_message_id=f"revision-dry-{len(sent_bodies)}")

    monkeypatch.setattr("app.services.notification_dispatch.DummyNotifier.send", fake_send)

    session = _build_session()
    seed_smoke_notifications(session)

    result = dispatch_notifications(session)

    assert result["sent"] == 4
    combined = "\n".join(sent_bodies)
    assert "[業績修正]" not in combined
    assert "売上高:" not in combined
    assert "中間配当:" not in combined
    assert "analysis_alert_revision_body_dry_run" in caplog.text
