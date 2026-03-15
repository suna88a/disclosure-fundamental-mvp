import argparse

from app.jobs.runner import run_job
from app.services.company_loader import load_companies_from_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load companies from a CSV file.")
    parser.add_argument(
        "--input",
        default="data/samples/companies_sample.csv",
        help="Path to the companies CSV file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    def job(context):
        result = load_companies_from_csv(context.session, args.input)
        context.set_processed_count(result["inserted"] + result["updated"])
        return result

    result = run_job("load_companies", job)
    print(result)


if __name__ == "__main__":
    main()
