import argparse

from app.jobs.runner import run_job
from app.services.disclosure_classification_service import reclassify_disclosures
from app.services.disclosure_classifier import DisclosureClassifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reclassify existing disclosures.")
    parser.add_argument(
        "--only-unclassified",
        action="store_true",
        help="Process only records without a category.",
    )
    parser.add_argument(
        "--rules",
        default=None,
        help="Optional path to a custom classification rules JSON file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    classifier = DisclosureClassifier(args.rules)

    def job(context):
        result = reclassify_disclosures(
            context.session,
            classifier=classifier,
            only_unclassified=args.only_unclassified,
        )
        context.set_processed_count(result["processed"])
        return result

    result = run_job("reclassify_disclosures", job)
    print(result)


if __name__ == "__main__":
    main()
