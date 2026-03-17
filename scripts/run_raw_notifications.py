import argparse
from datetime import date

from app.jobs.runner import run_job
from app.services.notification_dispatch import dispatch_raw_disclosure_notifications


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch batched raw disclosure notifications.")
    parser.add_argument("--lookback-minutes", type=int, default=None, help="Look back this many minutes using disclosure created_at.")
    parser.add_argument("--date", default="", help="Replay or backfill disclosures for one JST date (YYYY-MM-DD).")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_date = date.fromisoformat(args.date) if args.date else None

    def job(context):
        result = dispatch_raw_disclosure_notifications(
            context.session,
            lookback_minutes=args.lookback_minutes,
            target_date=target_date,
        )
        context.set_processed_count(result["processed"])
        return result

    result = run_job("dispatch_raw_notifications", job)
    print(result)


if __name__ == "__main__":
    main()
