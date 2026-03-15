from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.repositories.valuation_view_repository import ValuationViewRepository
from app.services.valuation_view_builder import build_valuation_view


def ingest_valuation_views(session: Session) -> dict[str, int]:
    analyses = list(
        session.scalars(
            select(AnalysisResult)
            .join(AnalysisResult.disclosure)
            .join(Disclosure.company)
            .where(Company.is_active.is_(True))
        )
    )
    repository = ValuationViewRepository(session)

    processed = 0
    saved = 0
    for analysis in analyses:
        processed += 1
        built = build_valuation_view(analysis)
        repository.upsert(
            analysis.disclosure_id,
            eps_revision_potential=built.eps_revision_potential,
            eps_revision_view=built.eps_revision_view,
            acceptable_per_direction=built.acceptable_per_direction,
            per_change_view=built.per_change_view,
            short_term_reaction=built.short_term_reaction,
            short_term_reaction_view=built.short_term_reaction_view,
            valuation_comment=built.valuation_comment,
        )
        saved += 1

    session.flush()
    session.expire_all()
    return {"processed": processed, "saved": saved}
