import argparse
import os
from datetime import date

from app.fetchers.disclosure_fetcher import (
    DEFAULT_USER_AGENT,
    DummyDisclosureFetcher,
    HttpJsonDisclosureFetcher,
    JpxTdnetDisclosureFetcher,
)
from app.jobs.runner import run_job
from app.services.disclosure_ingestion import ingest_disclosures


DEFAULT_SOURCE = "jpx-tdnet" if os.getenv("JPX_DISCLOSURE_URL_TEMPLATE") else ("http-json" if os.getenv("DISCLOSURE_SOURCE_URL") else "dummy")



def _parse_date(value: str) -> date:
    return date.fromisoformat(value)



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and persist disclosures.")
    parser.add_argument("--source", default=DEFAULT_SOURCE, choices=["dummy", "http-json", "jpx-tdnet"], help="Disclosure source backend.")
    parser.add_argument("--input", default="data/samples/disclosures_sample.json", help="Input file path for the dummy source.")
    parser.add_argument("--url", default=os.getenv("DISCLOSURE_SOURCE_URL", ""), help="HTTP JSON disclosure feed URL for the http-json source.")
    parser.add_argument("--url-template", default=os.getenv("JPX_DISCLOSURE_URL_TEMPLATE", ""), help="JPX TDnet list URL template. Supports {date} (YYYY-MM-DD), {date_yyyymmdd} (YYYYMMDD), and optional {page}.")
    parser.add_argument("--date", dest="target_date", type=_parse_date, help="Target date in YYYY-MM-DD format. Defaults to today in JST.")
    parser.add_argument("--date-from", type=_parse_date, help="Range start date in YYYY-MM-DD format.")
    parser.add_argument("--date-to", type=_parse_date, help="Range end date in YYYY-MM-DD format.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds for real fetchers.")
    parser.add_argument("--retry-count", type=int, default=2, help="Retry count for JPX TDnet HTTP fetches.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="User-Agent string for JPX TDnet HTTP fetches.")
    return parser.parse_args()



def build_fetcher(args: argparse.Namespace):
    if args.source == "dummy":
        return DummyDisclosureFetcher(args.input)
    if args.source == "http-json":
        if not args.url:
            raise ValueError("--url or DISCLOSURE_SOURCE_URL is required when --source=http-json.")
        return HttpJsonDisclosureFetcher(args.url, timeout=args.timeout)
    if args.source == "jpx-tdnet":
        if not args.url_template:
            raise ValueError("--url-template or JPX_DISCLOSURE_URL_TEMPLATE is required when --source=jpx-tdnet.")
        return JpxTdnetDisclosureFetcher(
            args.url_template,
            target_date=args.target_date,
            date_from=args.date_from,
            date_to=args.date_to,
            timeout=args.timeout,
            retry_count=args.retry_count,
            user_agent=args.user_agent,
        )
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
