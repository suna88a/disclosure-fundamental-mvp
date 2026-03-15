from sqlalchemy.exc import OperationalError

from app.db import session_scope
from app.services.failure_summary_report import (
    render_failure_summary,
    summarize_comparison_errors,
    summarize_pdf_parse_failures,
)


def main() -> None:
    try:
        with session_scope() as session:
            comparison_summary = summarize_comparison_errors(session)
            pdf_summary = summarize_pdf_parse_failures(session)
        print(render_failure_summary(comparison_summary, pdf_summary))
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
