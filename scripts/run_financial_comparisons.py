from app.jobs.runner import run_job
from app.services.financial_comparison_ingestion import ingest_financial_comparisons


def main() -> None:
    def job(context):
        result = ingest_financial_comparisons(context.session)
        context.set_processed_count(result["processed"])
        return result

    result = run_job("run_financial_comparisons", job)
    print(result)


if __name__ == "__main__":
    main()
