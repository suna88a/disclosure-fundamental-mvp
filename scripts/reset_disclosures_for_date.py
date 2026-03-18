from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models.analysis_result import AnalysisResult
from app.models.disclosure import Disclosure
from app.models.dividend_revision import DividendRevision
from app.models.financial_report import FinancialReport
from app.models.guidance_revision import GuidanceRevision
from app.models.notification import Notification
from app.models.pdf_file import PdfFile
from app.models.valuation_view import ValuationView

JST = ZoneInfo("Asia/Tokyo")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reset one disclosure day before refetching.")
    parser.add_argument("--date", required=True, help="Target JST date in YYYY-MM-DD format.")
    parser.add_argument("--apply", action="store_true", help="Actually delete rows. Without this flag the script only reports counts.")
    return parser.parse_args()



def reset_disclosures_for_date(session: Session, target_date: date, *, apply: bool = False) -> dict[str, int | str]:
    start_at = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=JST)
    end_at = start_at + timedelta(days=1)
    disclosure_ids = list(
        session.scalars(
            select(Disclosure.id).where(Disclosure.disclosed_at >= start_at, Disclosure.disclosed_at < end_at)
        )
    )

    result: dict[str, int | str] = {
        "target_date": target_date.isoformat(),
        "disclosures": len(disclosure_ids),
        "notifications": 0,
        "pdf_files": 0,
        "financial_reports": 0,
        "guidance_revisions": 0,
        "dividend_revisions": 0,
        "analysis_results": 0,
        "valuation_views": 0,
        "applied": int(apply),
    }
    if not disclosure_ids:
        return result

    result["notifications"] = _count_rows(session, Notification, disclosure_ids)
    result["pdf_files"] = _count_rows(session, PdfFile, disclosure_ids)
    result["financial_reports"] = _count_rows(session, FinancialReport, disclosure_ids)
    result["guidance_revisions"] = _count_rows(session, GuidanceRevision, disclosure_ids)
    result["dividend_revisions"] = _count_rows(session, DividendRevision, disclosure_ids)
    result["analysis_results"] = _count_rows(session, AnalysisResult, disclosure_ids)
    result["valuation_views"] = _count_rows(session, ValuationView, disclosure_ids)

    if not apply:
        return result

    session.execute(delete(Notification).where(Notification.disclosure_id.in_(disclosure_ids)))
    session.execute(delete(ValuationView).where(ValuationView.disclosure_id.in_(disclosure_ids)))
    session.execute(delete(AnalysisResult).where(AnalysisResult.disclosure_id.in_(disclosure_ids)))
    session.execute(delete(DividendRevision).where(DividendRevision.disclosure_id.in_(disclosure_ids)))
    session.execute(delete(GuidanceRevision).where(GuidanceRevision.disclosure_id.in_(disclosure_ids)))
    session.execute(delete(FinancialReport).where(FinancialReport.disclosure_id.in_(disclosure_ids)))
    session.execute(delete(PdfFile).where(PdfFile.disclosure_id.in_(disclosure_ids)))
    session.execute(delete(Disclosure).where(Disclosure.id.in_(disclosure_ids)))
    return result



def _count_rows(session: Session, model, disclosure_ids: list[int]) -> int:
    return len(list(session.scalars(select(model.id).where(model.disclosure_id.in_(disclosure_ids)))))



def main() -> None:
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    with session_scope() as session:
        result = reset_disclosures_for_date(session, target_date, apply=args.apply)
    print(result)
    if not args.apply:
        print("Dry run only. Re-run with --apply to delete rows for this disclosure date.")


if __name__ == "__main__":
    main()
