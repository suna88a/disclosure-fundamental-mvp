from sqlalchemy.orm import Session

from app.fetchers.disclosure_fetcher import DisclosureFetcher
from app.repositories.disclosure_repository import DisclosureCreateInput, DisclosureRepository
from app.services.disclosure_classifier import DisclosureClassifier


def ingest_disclosures(session: Session, fetcher: DisclosureFetcher) -> dict[str, int]:
    fetched = fetcher.fetch()
    repository = DisclosureRepository(session)
    classifier = DisclosureClassifier()
    payloads = []
    for record in fetched:
        classified = classifier.classify(record.title)
        payloads.append(
            DisclosureCreateInput(
                company_code=record.company_code,
                source_name=record.source_name,
                disclosed_at=record.disclosed_at,
                title=record.title,
                source_url=record.source_url,
                source_disclosure_id=record.source_disclosure_id,
                normalized_title=classified.normalized_title,
                classification_reason=classified.classification_reason,
                category=classified.category,
                priority=classified.priority,
                is_analysis_target=classified.is_analysis_target,
            )
        )
    result = repository.bulk_upsert(payloads)
    result["fetched"] = len(payloads)
    return result
