from app.jobs.runner import run_job
from app.services.valuation_view_ingestion import ingest_valuation_views


def main() -> None:
    def job(context):
        result = ingest_valuation_views(context.session)
        context.set_processed_count(result["processed"])
        return result

    result = run_job("build_valuation_views", job)
    print(result)


if __name__ == "__main__":
    main()
