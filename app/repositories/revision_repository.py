from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dividend_revision import DividendRevision
from app.models.guidance_revision import GuidanceRevision


class RevisionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_guidance_revision(self, disclosure_id: int) -> GuidanceRevision | None:
        return self.session.scalar(
            select(GuidanceRevision).where(GuidanceRevision.disclosure_id == disclosure_id)
        )

    def get_dividend_revision(self, disclosure_id: int) -> DividendRevision | None:
        return self.session.scalar(
            select(DividendRevision).where(DividendRevision.disclosure_id == disclosure_id)
        )

    def upsert_guidance_revision(self, disclosure_id: int, **payload: object) -> GuidanceRevision:
        revision = self.get_guidance_revision(disclosure_id)
        if revision is None:
            revision = GuidanceRevision(disclosure_id=disclosure_id)
            self.session.add(revision)

        for key, value in payload.items():
            setattr(revision, key, value)

        self.session.flush()
        return revision

    def upsert_dividend_revision(self, disclosure_id: int, **payload: object) -> DividendRevision:
        revision = self.get_dividend_revision(disclosure_id)
        if revision is None:
            revision = DividendRevision(disclosure_id=disclosure_id)
            self.session.add(revision)

        for key, value in payload.items():
            setattr(revision, key, value)

        self.session.flush()
        return revision
