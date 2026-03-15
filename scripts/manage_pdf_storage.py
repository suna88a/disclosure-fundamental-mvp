from __future__ import annotations

import argparse
from pathlib import Path

from app.db import session_scope
from app.services.maintenance import (
    build_pdf_storage_report,
    delete_orphan_pdfs,
    format_size_mb,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect and optionally delete orphan PDF files.")
    parser.add_argument(
        "--root-dir",
        default="data/pdf",
        help="PDF storage root directory.",
    )
    parser.add_argument(
        "--delete-orphans",
        action="store_true",
        help="Delete orphan PDF files. Default is dry-run only.",
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=7,
        help="Delete only orphan files older than this many days.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root_dir = Path(args.root_dir)
    with session_scope() as session:
        report = build_pdf_storage_report(session, root_dir)

    print(
        {
            "root_dir": str(report.root_dir),
            "total_files": report.total_files,
            "total_size": format_size_mb(report.total_size_bytes),
            "referenced_files": report.referenced_files,
            "referenced_size": format_size_mb(report.referenced_size_bytes),
            "orphan_files": len(report.orphan_files),
            "orphan_size": format_size_mb(sum(item.size_bytes for item in report.orphan_files)),
        }
    )

    if not args.delete_orphans:
        for item in report.orphan_files[:20]:
            print(f"DRY-RUN orphan: {item.path} ({format_size_mb(item.size_bytes)})")
        return

    deleted = delete_orphan_pdfs(report.orphan_files, older_than_days=args.older_than_days)
    print({"deleted_orphans": [str(path) for path in deleted], "deleted_count": len(deleted)})


if __name__ == "__main__":
    main()
