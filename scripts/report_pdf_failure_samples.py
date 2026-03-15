import argparse

from sqlalchemy.exc import OperationalError

from app.db import session_scope
from app.services.failure_summary_report import (
    collect_pdf_parse_failure_samples,
    render_pdf_parse_failure_samples,
)



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show representative failed PDF parse samples grouped by parse_error_code."
    )
    parser.add_argument(
        "--code",
        help="Filter by parse_error_code, e.g. unsupported_format",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of samples to show per code (default: 5)",
    )
    return parser



def main() -> None:
    args = build_parser().parse_args()
    try:
        with session_scope() as session:
            report = collect_pdf_parse_failure_samples(
                session,
                code=args.code,
                limit=max(args.limit, 1),
            )
        print(render_pdf_parse_failure_samples(report))
    except OperationalError as exc:
        message = str(exc).lower()
        if "no such column" in message or "no such table" in message:
            raise SystemExit(
                "Schema mismatch detected. Recreate the SQLite DB with "
                "`python -m scripts.init_db` and reload sample/master data before running this report."
            ) from exc
        raise


if __name__ == "__main__":
    main()
