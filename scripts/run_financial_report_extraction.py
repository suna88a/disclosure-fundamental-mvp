import argparse

from app.fetchers.financial_report_parser import DummyFinancialReportParser
from app.jobs.runner import run_job
from app.services.financial_report_ingestion import ingest_financial_reports


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract financial reports from earnings PDFs.")
    parser.add_argument(
        "--source",
        default="dummy",
        choices=["dummy"],
        help="Financial report parser backend.",
    )
    parser.add_argument(
        "--manifest",
        default="data/samples/financial_reports_sample.json",
        help="Dummy manifest path for financial report extraction.",
    )
    return parser.parse_args()


def build_parser(args: argparse.Namespace) -> DummyFinancialReportParser:
    if args.source == "dummy":
        return DummyFinancialReportParser(args.manifest)
    raise ValueError(f"Unsupported source: {args.source}")


def main() -> None:
    args = parse_args()
    parser = build_parser(args)

    def job(context):
        result = ingest_financial_reports(context.session, parser)
        context.set_processed_count(result["processed"])
        return result

    result = run_job("extract_financial_reports", job)
    print(result)


if __name__ == "__main__":
    main()
