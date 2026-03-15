from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.jobs import runner
from app.models.enums import JobStatus
from app.models.job_run import JobRun


def test_run_job_persists_result_summary_json(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(runner, "SessionLocal", testing_session_local)

    result = runner.run_job(
        "sample_job",
        lambda context: {"processed": 5, "inserted": 2, "skipped_inactive": 1},
    )

    with testing_session_local() as session:
        job_run = session.scalar(select(JobRun).where(JobRun.job_name == "sample_job"))

    assert result["processed"] == 5
    assert job_run is not None
    assert job_run.status == JobStatus.SUCCESS
    assert '"processed": 5' in job_run.result_summary_json
    assert '"skipped_inactive": 1' in job_run.result_summary_json
