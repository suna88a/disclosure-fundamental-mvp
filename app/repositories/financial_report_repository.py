from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.financial_report import FinancialReport


class FinancialReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_disclosure_id(self, disclosure_id: int) -> FinancialReport | None:
        return self.session.scalar(
            select(FinancialReport).where(FinancialReport.disclosure_id == disclosure_id)
        )

    def upsert(self, disclosure_id: int, **payload: object) -> FinancialReport:
        report = self.get_by_disclosure_id(disclosure_id)
        if report is None:
            report = FinancialReport(disclosure_id=disclosure_id)
            self.session.add(report)

        for key, value in payload.items():
            setattr(report, key, value)

        self.session.flush()
        return report
