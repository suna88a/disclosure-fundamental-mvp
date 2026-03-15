from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.disclosure import Disclosure
from app.services.disclosure_classifier import DisclosureClassifier


def reclassify_disclosures(
    session: Session,
    classifier: DisclosureClassifier,
    only_unclassified: bool = False,
) -> dict[str, int]:
    statement = select(Disclosure)
    if only_unclassified:
        statement = statement.where(Disclosure.category.is_(None))

    disclosures = list(session.scalars(statement))
    updated = 0
    analysis_target_count = 0

    for disclosure in disclosures:
        result = classifier.classify(disclosure.title)
        disclosure.normalized_title = result.normalized_title
        disclosure.category = result.category
        disclosure.priority = result.priority
        disclosure.is_analysis_target = result.is_analysis_target
        disclosure.classification_reason = result.classification_reason
        updated += 1
        if result.is_analysis_target:
            analysis_target_count += 1

    session.flush()
    return {
        "processed": len(disclosures),
        "updated": updated,
        "analysis_targets": analysis_target_count,
    }
