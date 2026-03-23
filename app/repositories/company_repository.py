from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_code(self, code: str) -> Company | None:
        statement = select(Company).where(Company.code == code)
        return self.session.scalar(statement)

    def list_active_codes(self) -> list[str]:
        statement = select(Company.code).where(Company.is_active.is_(True)).order_by(Company.code.asc())
        return [str(code) for code in self.session.scalars(statement)]

    def bulk_upsert(self, companies: Sequence[dict[str, str | bool | None]]) -> dict[str, int]:
        inserted = 0
        updated = 0

        for payload in companies:
            code = str(payload["code"])
            company = self.get_by_code(code)
            if company is None:
                company = Company(
                    code=code,
                    name_ja=self._optional_string(payload.get("name_ja") or payload.get("name_jp")),
                    name=str(payload["name"]),
                    market=self._optional_string(payload.get("market")),
                    industry=self._optional_string(payload.get("industry")),
                    is_active=bool(payload.get("is_active", True)),
                )
                self.session.add(company)
                inserted += 1
                continue

            company.name_ja = self._optional_string(payload.get("name_ja") or payload.get("name_jp"))
            company.name = str(payload["name"])
            company.market = self._optional_string(payload.get("market"))
            company.industry = self._optional_string(payload.get("industry"))
            company.is_active = bool(payload.get("is_active", True))
            updated += 1

        self.session.flush()
        return {"inserted": inserted, "updated": updated}

    @staticmethod
    def _optional_string(value: str | bool | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
