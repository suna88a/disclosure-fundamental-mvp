from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.valuation_view import ValuationView


class ValuationViewRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_disclosure_id(self, disclosure_id: int) -> ValuationView | None:
        return self.session.scalar(
            select(ValuationView).where(ValuationView.disclosure_id == disclosure_id)
        )

    def upsert(self, disclosure_id: int, **payload: object) -> ValuationView:
        valuation_view = self.get_by_disclosure_id(disclosure_id)
        if valuation_view is None:
            valuation_view = ValuationView(disclosure_id=disclosure_id)
            self.session.add(valuation_view)

        for key, value in payload.items():
            setattr(valuation_view, key, value)

        self.session.flush()
        return valuation_view
