from __future__ import annotations

import argparse
from pathlib import Path

from app.config import get_settings
from app.services.maintenance import create_sqlite_backup, resolve_sqlite_db_path, rotate_backup_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a SQLite backup and rotate old backup files.")
    parser.add_argument(
        "--backup-dir",
        default="data/backups",
        help="Directory where SQLite backup files are stored.",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="How many recent backup files to keep.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    source_path = resolve_sqlite_db_path(settings.database_url)
    backup_dir = Path(args.backup_dir)

    backup_path = create_sqlite_backup(source_path, backup_dir)
    removed = rotate_backup_files(backup_dir, keep=args.keep, stem=source_path.stem)
    print(
        {
            "backup_path": str(backup_path),
            "removed_old_backups": [str(path) for path in removed],
        }
    )


if __name__ == "__main__":
    main()
