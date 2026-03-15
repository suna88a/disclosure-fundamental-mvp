from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.fetchers.revision_extractor import (
    DividendRevisionPayload,
    GuidanceRevisionPayload,
    RevisionExtractor,
)
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory
from app.repositories.analysis_result_repository import AnalysisResultRepository
from app.repositories.revision_repository import RevisionRepository
from app.services.revision_analysis_service import build_analysis_payload


TARGET_CATEGORIES = (
    DisclosureCategory.GUIDANCE_REVISION,
    DisclosureCategory.DIVIDEND_REVISION,
)


def ingest_revisions(session: Session, extractor: RevisionExtractor) -> dict[str, int]:
    disclosures = list(
        session.scalars(
            select(Disclosure)
            .join(Disclosure.company)
            .where(
                Company.is_active.is_(True),
                Disclosure.category.in_(TARGET_CATEGORIES),
                Disclosure.is_analysis_target.is_(True),
            )
        )
    )

    revision_repository = RevisionRepository(session)
    analysis_repository = AnalysisResultRepository(session)

    guidance_saved = 0
    dividend_saved = 0
    analysis_saved = 0
    no_payload = 0

    for disclosure in disclosures:
        extracted = extractor.extract(disclosure)
        guidance_payload = extracted.guidance_revision
        dividend_payload = extracted.dividend_revision

        if guidance_payload is None and dividend_payload is None:
            no_payload += 1
            continue

        if guidance_payload is not None:
            revision_repository.upsert_guidance_revision(
                disclosure.id, **_guidance_payload_dict(guidance_payload)
            )
            guidance_saved += 1

        if dividend_payload is not None:
            revision_repository.upsert_dividend_revision(
                disclosure.id, **_dividend_payload_dict(dividend_payload)
            )
            dividend_saved += 1

        analysis_payload = build_analysis_payload(
            guidance_payload=guidance_payload,
            dividend_payload=dividend_payload,
            extraction_reason=extracted.extraction_reason,
        )
        analysis_repository.upsert(disclosure.id, **analysis_payload)
        analysis_saved += 1

    session.flush()
    return {
        "processed": len(disclosures),
        "guidance_saved": guidance_saved,
        "dividend_saved": dividend_saved,
        "analysis_saved": analysis_saved,
        "no_payload": no_payload,
    }


def _guidance_payload_dict(payload: GuidanceRevisionPayload) -> dict[str, object]:
    return asdict(payload)


def _dividend_payload_dict(payload: DividendRevisionPayload) -> dict[str, object]:
    return asdict(payload)
