import csv
from pathlib import Path

from sqlalchemy.orm import Session

from app.repositories.company_repository import CompanyRepository


def load_companies_from_csv(session: Session, csv_path: str | Path) -> dict[str, int]:
    path = Path(csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required_columns = {"code", "name"}
        missing_columns = sorted(required_columns - set(reader.fieldnames or []))
        if missing_columns:
            raise ValueError(f"Missing required columns in companies CSV: {', '.join(missing_columns)}")

        payloads = []
        for row in reader:
            code = row["code"].strip()
            name = row["name"].strip()
            if not code or not name:
                raise ValueError("Each companies CSV row must include non-empty code and name.")
            payloads.append(
                {
                    "code": code,
                    "name": name,
                    "name_ja": row.get("name_ja", "").strip() or row.get("name_jp", "").strip() or None,
                    "market": row.get("market", "").strip() or None,
                    "industry": row.get("industry", "").strip() or None,
                    "is_active": _to_bool(row.get("is_active", "true")),
                }
            )
    repository = CompanyRepository(session)
    return repository.bulk_upsert(payloads)


def _to_bool(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no"}
