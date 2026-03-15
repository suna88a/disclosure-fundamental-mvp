from app.jobs.runner import run_job
from app.services.notification_dispatch import dispatch_notifications


def main() -> None:
    def job(context):
        result = dispatch_notifications(context.session)
        context.set_processed_count(result["processed"])
        return result

    result = run_job("dispatch_notifications", job)
    print(result)


if __name__ == "__main__":
    main()
