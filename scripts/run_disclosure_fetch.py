import argparse

from app.fetchers.disclosure_fetcher import DummyDisclosureFetcher
from app.jobs.runner import run_job
from app.services.disclosure_ingestion import ingest_disclosures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and persist disclosures.")
    parser.add_argument(
        "--source",
        default="dummy",
        choices=["dummy"],
        help="Disclosure source backend.",
    )
    parser.add_argument(
        "--input",
        default="data/samples/disclosures_sample.json",
        help="Input file path for the dummy source.",
    )
    return parser.parse_args()


def build_fetcher(args: argparse.Namespace) -> DummyDisclosureFetcher:
    if args.source == "dummy":
        return DummyDisclosureFetcher(args.input)
    raise ValueError(f"Unsupported source: {args.source}")


def main() -> None:
    args = parse_args()
    fetcher = build_fetcher(args)

    def job(context):
        result = ingest_disclosures(context.session, fetcher)
        context.set_processed_count(result["fetched"])
        return result

    result = run_job("fetch_disclosures", job)
    print(result)


if __name__ == "__main__":
    main()
