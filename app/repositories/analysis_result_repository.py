from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult


class AnalysisResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_disclosure_id(self, disclosure_id: int) -> AnalysisResult | None:
        return self.session.scalar(
            select(AnalysisResult).where(AnalysisResult.disclosure_id == disclosure_id)
        )

    def upsert(self, disclosure_id: int, **payload: object) -> AnalysisResult:
        analysis_result = self.get_by_disclosure_id(disclosure_id)
        if analysis_result is None:
            analysis_result = AnalysisResult(disclosure_id=disclosure_id)
            self.session.add(analysis_result)

        for key, value in payload.items():
            setattr(analysis_result, key, value)

        self.session.flush()
        return analysis_result
