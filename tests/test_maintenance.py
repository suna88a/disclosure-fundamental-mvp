from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory, DisclosurePriority
from app.models.pdf_file import PdfFile
from app.services.maintenance import (
    build_pdf_storage_report,
    create_sqlite_backup,
    delete_orphan_pdfs,
    resolve_sqlite_db_path,
    rotate_backup_files,
)


def make_test_dir() -> Path:
    path = Path("data") / f"maintenance_test_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path.resolve()


def test_resolve_sqlite_db_path() -> None:
    base = make_test_dir()
    try:
        result = resolve_sqlite_db_path("sqlite:///./data/app.db", cwd=base)
        assert result == (base / "data" / "app.db").resolve()
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_create_sqlite_backup_and_rotate() -> None:
    base = make_test_dir()
    try:
        source = base / "app.db"
        connection = sqlite3.connect(source)
        try:
            connection.execute("create table sample(id integer primary key)")
            connection.execute("insert into sample(id) values (1)")
            connection.commit()
        finally:
            connection.close()

        backup_dir = base / "backups"
        first = create_sqlite_backup(source, backup_dir, timestamp=datetime(2026, 3, 14, 1, 0, tzinfo=UTC))
        second = create_sqlite_backup(source, backup_dir, timestamp=datetime(2026, 3, 14, 2, 0, tzinfo=UTC))
        removed = rotate_backup_files(backup_dir, keep=1, stem=source.stem)

        assert first.exists() is False
        assert second.exists() is True
        assert removed == [first]
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_build_pdf_storage_report_and_delete_orphans() -> None:
    base = make_test_dir()
    try:
        database_path = base / "test.db"
        engine = create_engine(f"sqlite:///{database_path}", future=True)
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine, future=True)

        pdf_root = base / "pdf"
        pdf_root.mkdir()
        referenced_file = pdf_root / "referenced.pdf"
        referenced_file.write_bytes(b"pdf-a")
        orphan_file = pdf_root / "orphan.pdf"
        orphan_file.write_bytes(b"pdf-b")

        old_timestamp = (datetime.now(UTC) - timedelta(days=30)).timestamp()
        os.utime(orphan_file, (old_timestamp, old_timestamp))

        with session_factory() as session:
            company = Company(code="7203", name="Test Company")
            session.add(company)
            session.flush()

            disclosure = Disclosure(
                company_id=company.id,
                source_name="dummy",
                disclosed_at=datetime.now(UTC),
                title="Test",
                normalized_title="test",
                classification_reason="rule",
                category=DisclosureCategory.EARNINGS_REPORT,
                priority=DisclosurePriority.HIGH,
                source_url="https://example.com",
                is_new=True,
                is_analysis_target=True,
            )
            session.add(disclosure)
            session.flush()

            pdf_file = PdfFile(
                disclosure_id=disclosure.id,
                source_url="https://example.com/test.pdf",
                file_path=str(referenced_file),
            )
            session.add(pdf_file)
            session.commit()

            report = build_pdf_storage_report(session, pdf_root)

        assert report.total_files == 2
        assert report.referenced_files == 1
        assert len(report.orphan_files) == 1
        assert report.orphan_files[0].path == orphan_file.resolve()

        deleted = delete_orphan_pdfs(report.orphan_files, older_than_days=7)
        assert deleted == [orphan_file.resolve()]
        assert orphan_file.exists() is False
    finally:
        shutil.rmtree(base, ignore_errors=True)
