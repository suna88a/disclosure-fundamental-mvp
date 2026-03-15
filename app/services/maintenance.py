from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pdf_file import PdfFile


def resolve_sqlite_db_path(database_url: str, cwd: Path | None = None) -> Path:
    sqlite_prefix = "sqlite:///"
    if not database_url.startswith(sqlite_prefix):
        raise ValueError("Only sqlite:/// URLs are supported for backup maintenance.")

    raw_path = database_url[len(sqlite_prefix) :]
    if raw_path == ":memory:":
        raise ValueError("In-memory SQLite databases are not supported for backup maintenance.")

    db_path = Path(raw_path)
    if not db_path.is_absolute():
        base_dir = cwd or Path.cwd()
        db_path = base_dir / db_path
    return db_path.resolve()


def create_sqlite_backup(source_path: Path, backup_dir: Path, timestamp: datetime | None = None) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {source_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    current_time = timestamp or datetime.now(UTC)
    backup_path = backup_dir / f"{source_path.stem}-{current_time.strftime('%Y%m%d-%H%M%S')}.db"

    source_connection = sqlite3.connect(source_path)
    try:
        backup_connection = sqlite3.connect(backup_path)
        try:
            source_connection.backup(backup_connection)
        finally:
            backup_connection.close()
    finally:
        source_connection.close()

    return backup_path


def rotate_backup_files(backup_dir: Path, keep: int, stem: str) -> list[Path]:
    if keep < 1:
        raise ValueError("keep must be at least 1")

    backups = sorted(backup_dir.glob(f"{stem}-*.db"), key=lambda path: path.stat().st_mtime, reverse=True)
    removed: list[Path] = []
    for path in backups[keep:]:
        path.unlink(missing_ok=True)
        removed.append(path)
    return removed


@dataclass(frozen=True)
class PdfStorageFileInfo:
    path: Path
    size_bytes: int
    referenced: bool


@dataclass(frozen=True)
class PdfStorageReport:
    root_dir: Path
    total_files: int
    total_size_bytes: int
    referenced_files: int
    referenced_size_bytes: int
    orphan_files: list[PdfStorageFileInfo]


def build_pdf_storage_report(session: Session, root_dir: Path) -> PdfStorageReport:
    root_dir = root_dir.resolve()
    referenced_paths: set[Path] = set()

    for file_path in session.scalars(select(PdfFile.file_path).where(PdfFile.file_path.is_not(None))):
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        else:
            candidate = candidate.resolve()
        referenced_paths.add(candidate)

    orphan_files: list[PdfStorageFileInfo] = []
    total_files = 0
    total_size_bytes = 0
    referenced_files = 0
    referenced_size_bytes = 0

    if root_dir.exists():
        for path in root_dir.rglob("*.pdf"):
            if not path.is_file():
                continue
            total_files += 1
            size = path.stat().st_size
            total_size_bytes += size
            resolved_path = path.resolve()
            if resolved_path in referenced_paths:
                referenced_files += 1
                referenced_size_bytes += size
                continue
            orphan_files.append(PdfStorageFileInfo(path=resolved_path, size_bytes=size, referenced=False))

    orphan_files.sort(key=lambda item: item.path.stat().st_mtime, reverse=False)
    return PdfStorageReport(
        root_dir=root_dir,
        total_files=total_files,
        total_size_bytes=total_size_bytes,
        referenced_files=referenced_files,
        referenced_size_bytes=referenced_size_bytes,
        orphan_files=orphan_files,
    )


def delete_orphan_pdfs(orphan_files: list[PdfStorageFileInfo], older_than_days: int | None = None) -> list[Path]:
    cutoff: datetime | None = None
    if older_than_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

    deleted: list[Path] = []
    for item in orphan_files:
        modified_at = datetime.fromtimestamp(item.path.stat().st_mtime, tz=UTC)
        if cutoff is not None and modified_at >= cutoff:
            continue
        item.path.unlink(missing_ok=True)
        deleted.append(item.path)
    return deleted


def format_size_mb(size_bytes: int) -> str:
    return f"{size_bytes / (1024 * 1024):.2f} MB"
