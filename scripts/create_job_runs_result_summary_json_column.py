from sqlalchemy import inspect, text

from app.db import engine


COLUMN_NAME = "result_summary_json"
TABLE_NAME = "job_runs"


def main() -> None:
    inspector = inspect(engine)
    if not inspector.has_table(TABLE_NAME):
        raise RuntimeError("job_runs table does not exist. Run scripts.init_db first.")

    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    if COLUMN_NAME in columns:
        print("job_runs.result_summary_json column already exists.")
        return

    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {COLUMN_NAME} TEXT"))

    print("job_runs.result_summary_json column ensured.")


if __name__ == "__main__":
    main()
