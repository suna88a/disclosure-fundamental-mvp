import argparse

from app.fetchers.revision_extractor import DummyRevisionExtractor
from app.jobs.runner import run_job
from app.services.revision_ingestion import ingest_revisions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract standalone revision disclosures.")
    parser.add_argument(
        "--source",
        default="dummy",
        choices=["dummy"],
        help="Revision extraction backend.",
    )
    parser.add_argument(
        "--manifest",
        default="data/samples/revision_extractions_sample.json",
        help="Dummy manifest for revision extraction.",
    )
    return parser.parse_args()


def build_extractor(args: argparse.Namespace) -> DummyRevisionExtractor:
    if args.source == "dummy":
        return DummyRevisionExtractor(args.manifest)
    raise ValueError(f"Unsupported source: {args.source}")


def main() -> None:
    args = parse_args()
    extractor = build_extractor(args)

    def job(context):
        result = ingest_revisions(context.session, extractor)
        context.set_processed_count(result["processed"])
        return result

    result = run_job("extract_revisions", job)
    print(result)


if __name__ == "__main__":
    main()
