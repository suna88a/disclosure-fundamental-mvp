import argparse
from datetime import date

from app.jobs.runner import run_job
from app.services.notification_dispatch import dispatch_raw_disclosure_notifications


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch batched raw disclosure notifications.")
    parser.add_argument("--lookback-minutes", type=int, default=None, help="Look back this many minutes using disclosure created_at.")
    parser.add_argument("--date", default="", help="Replay or backfill disclosures for one JST date (YYYY-MM-DD).")
    parser.add_argument("--force", action="store_true", help="Ignore raw notification dedupe and resend the selected disclosures.")
    parser.add_argument("--dry-run", action="store_true", help="Preview candidate counts without creating notification rows or sending webhooks.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_date = date.fromisoformat(args.date) if args.date else None

    def job(context):
        result = dispatch_raw_disclosure_notifications(
            context.session,
            lookback_minutes=args.lookback_minutes,
            target_date=target_date,
            force=args.force,
            dry_run=args.dry_run,
        )
        context.set_processed_count(result["processed"])
        return result

    result = run_job("dispatch_raw_notifications", job)
    print(result)


if __name__ == "__main__":
    main()
