from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.job_run import JobRun
from app.models.enums import JobStatus


T = TypeVar("T")


@dataclass
class JobContext:
    session: Session
    job_run: JobRun

    def set_processed_count(self, count: int) -> None:
        self.job_run.processed_count = count

    def increment_processed_count(self, step: int = 1) -> None:
        self.job_run.processed_count += step


def run_job(job_name: str, job_callable: Callable[[JobContext], T]) -> T:
    session = SessionLocal()
    try:
        job_run = JobRun(
            job_name=job_name,
            status=JobStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        session.add(job_run)
        session.commit()
        session.refresh(job_run)

        context = JobContext(session=session, job_run=job_run)
        try:
            result = job_callable(context)
            if isinstance(result, dict):
                job_run.result_summary_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
            job_run.status = JobStatus.SUCCESS
            job_run.finished_at = datetime.now(UTC)
            session.add(job_run)
            session.commit()
            return result
        except Exception as exc:
            processed_count = job_run.processed_count
            session.rollback()
            job_run.status = JobStatus.FAILED
            job_run.finished_at = datetime.now(UTC)
            job_run.processed_count = processed_count
            job_run.error_message = str(exc)
            session.add(job_run)
            session.commit()
            raise
    finally:
        session.close()
