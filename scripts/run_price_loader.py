import argparse
from datetime import datetime, date
from zoneinfo import ZoneInfo

from app.fetchers.price_fetcher import YFinancePriceFetcher
from app.jobs.runner import run_job
from app.repositories.company_repository import CompanyRepository
from app.services.price_loader import load_prices


JST = ZoneInfo("Asia/Tokyo")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and persist daily stock prices from a free source.")
    parser.add_argument("--source", default="yfinance", choices=["yfinance"], help="Price source backend.")
    parser.add_argument("--code", action="append", help="Target company code. Repeatable.")
    parser.add_argument("--date", dest="target_date", type=_parse_date, help="Single trade date in YYYY-MM-DD format.")
    parser.add_argument("--start-date", type=_parse_date, help="Range start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", type=_parse_date, help="Range end date in YYYY-MM-DD format.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch only and report what would be saved.")
    parser.add_argument("--force", action="store_true", help="Update existing price rows even when values are unchanged.")
    return parser.parse_args()


def _resolve_date_range(args: argparse.Namespace) -> tuple[date, date]:
    if args.target_date and (args.start_date or args.end_date):
        raise ValueError("Use either --date or --start-date/--end-date, not both.")
    if args.target_date:
        return args.target_date, args.target_date
    if args.start_date or args.end_date:
        if not args.start_date or not args.end_date:
            raise ValueError("Both --start-date and --end-date are required for range fetch.")
        if args.start_date > args.end_date:
            raise ValueError("--start-date must be earlier than or equal to --end-date.")
        return args.start_date, args.end_date
    today_jst = datetime.now(JST).date()
    return today_jst, today_jst


def _resolve_codes(args: argparse.Namespace, repository: CompanyRepository) -> list[str]:
    if args.code:
        return [str(code).strip() for code in args.code if str(code).strip()]
    return repository.list_active_codes()


def main() -> None:
    args = parse_args()
    start_date, end_date = _resolve_date_range(args)
    fetcher = YFinancePriceFetcher()

    def job(context):
        codes = _resolve_codes(args, CompanyRepository(context.session))
        result = load_prices(
            context.session,
            fetcher=fetcher,
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            dry_run=args.dry_run,
            force=args.force,
        )
        context.set_processed_count(result["fetched"])
        result["target_codes"] = len(codes)
        return result

    result = run_job("load_price_daily", job)
    print(result)


if __name__ == "__main__":
    main()
