import argparse
from datetime import date

from app.jobs.runner import run_job
from app.services.notification_dispatch import dispatch_daily_raw_digest_notifications


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch the daily raw disclosure digest for one JST date.")
    parser.add_argument("--date", default="", help="Target JST date in YYYY-MM-DD format. Defaults to today in JST.")
    parser.add_argument("--dry-run", action="store_true", help="Preview candidate counts without creating notification rows or sending webhooks.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_date = date.fromisoformat(args.date) if args.date else None

    def job(context):
        result = dispatch_daily_raw_digest_notifications(
            context.session,
            target_date=target_date,
            dry_run=args.dry_run,
        )
        context.set_processed_count(int(result["processed"]))
        return result

    result = run_job("dispatch_daily_raw_digest", job)
    print(result)


if __name__ == "__main__":
    main()
