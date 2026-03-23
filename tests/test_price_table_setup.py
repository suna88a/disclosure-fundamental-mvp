from sqlalchemy import create_engine, inspect, text

import app.db
from app.db import Base
from app.models.job_run import JobRun
from scripts import create_job_runs_result_summary_json_column, create_price_daily_table


def test_init_db_creates_price_daily_table(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    monkeypatch.setattr(app.db, "engine", engine)

    app.db.init_db()

    assert inspect(engine).has_table("price_daily")


def test_create_price_daily_table_script_is_create_only(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=[])
    monkeypatch.setattr(create_price_daily_table, "engine", engine)

    create_price_daily_table.main()

    assert inspect(engine).has_table("price_daily")
    create_price_daily_table.main()
    assert inspect(engine).has_table("price_daily")


def test_create_job_runs_result_summary_json_column_adds_missing_column(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE job_runs (
                id INTEGER PRIMARY KEY,
                job_name VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL,
                started_at DATETIME NOT NULL,
                finished_at DATETIME,
                processed_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            )
        """))
    monkeypatch.setattr(create_job_runs_result_summary_json_column, "engine", engine)

    create_job_runs_result_summary_json_column.main()

    column_names = {column["name"] for column in inspect(engine).get_columns("job_runs")}
    assert "result_summary_json" in column_names


def test_create_job_runs_result_summary_json_column_is_idempotent(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=[JobRun.__table__])
    monkeypatch.setattr(create_job_runs_result_summary_json_column, "engine", engine)

    create_job_runs_result_summary_json_column.main()
    create_job_runs_result_summary_json_column.main()

    column_names = [column["name"] for column in inspect(engine).get_columns("job_runs")]
    assert column_names.count("result_summary_json") == 1
