from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory, DisclosurePriority


@dataclass
class DisclosureCreateInput:
    company_code: str
    company_name: str | None
    source_name: str
    disclosed_at: datetime
    title: str
    source_url: str
    source_disclosure_id: str | None = None
    normalized_title: str | None = None
    classification_reason: str | None = None
    category: DisclosureCategory | None = None
    priority: DisclosurePriority | None = None
    is_analysis_target: bool = False


class DisclosureRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_company_by_code(self, code: str) -> Company | None:
        statement = select(Company).where(Company.code == code)
        return self.session.scalar(statement)

    def ensure_company_for_disclosure(self, payload: DisclosureCreateInput) -> tuple[Company, bool]:
        company = self.find_company_by_code(payload.company_code)
        if company is not None:
            self._refresh_company_names(company, payload.company_name)
            return company, False

        company_name = (payload.company_name or f"Unknown {payload.company_code}").strip()
        company = Company(
            code=payload.company_code,
            name=company_name,
            name_ja=company_name if payload.company_name else None,
            is_active=False,
        )
        self.session.add(company)
        self.session.flush()
        return company, True

    def _refresh_company_names(self, company: Company, company_name: str | None) -> None:
        normalized_name = (company_name or "").strip()
        if not normalized_name:
            return

        if self._should_refresh_name(company.name):
            company.name = normalized_name

        if not company.name_ja or self._should_refresh_name(company.name_ja):
            company.name_ja = normalized_name

    @staticmethod
    def _should_refresh_name(current_name: str | None) -> bool:
        if current_name is None:
            return True
        text = current_name.strip()
        if not text:
            return True
        if text.startswith("Unknown "):
            return True
        return DisclosureRepository._looks_mojibake(text)

    @staticmethod
    def _looks_mojibake(value: str) -> bool:
        normalized = unicodedata.normalize("NFKC", value)
        if "�" in normalized:
            return True
        latin_supplement = sum(1 for char in normalized if 0x00C0 <= ord(char) <= 0x024F)
        suspicious_markers = len(re.findall(r"[ÃÂÆÐÑØÞßæðøþŒœŠšŸž¢£¤¥¦§¨©«¬®¯°±²³´µ¶·¸»¼½¾]", normalized))
        has_japanese = any("ぁ" <= char <= "ゖ" or "ァ" <= char <= "ヿ" or "一" <= char <= "龯" for char in normalized)
        return not has_japanese and (suspicious_markers >= 1 or latin_supplement >= 3)

    def find_existing(self, payload: DisclosureCreateInput, company_id: int) -> Disclosure | None:
        if payload.source_disclosure_id:
            statement = select(Disclosure).where(
                Disclosure.source_disclosure_id == payload.source_disclosure_id
            )
            existing = self.session.scalar(statement)
            if existing is not None:
                return existing

        statement = select(Disclosure).where(
            Disclosure.source_name == payload.source_name,
            Disclosure.company_id == company_id,
            Disclosure.disclosed_at == payload.disclosed_at,
            Disclosure.title == payload.title,
        )
        return self.session.scalar(statement)

    def bulk_upsert(self, payloads: Sequence[DisclosureCreateInput]) -> dict[str, int]:
        inserted = 0
        skipped = 0
        skipped_inactive = 0
        autocreated_companies = 0
        seen_source_ids: set[str] = set()
        seen_fallback_keys: set[tuple[str, int, datetime, str]] = set()

        for payload in payloads:
            company, autocreated = self.ensure_company_for_disclosure(payload)
            if autocreated:
                autocreated_companies += 1

            fallback_key = (
                payload.source_name,
                company.id,
                payload.disclosed_at,
                payload.title,
            )
            if payload.source_disclosure_id and payload.source_disclosure_id in seen_source_ids:
                skipped += 1
                continue
            if fallback_key in seen_fallback_keys:
                skipped += 1
                continue

            existing = self.find_existing(payload, company.id)
            if existing is not None:
                existing.is_new = False
                skipped += 1
                if payload.source_disclosure_id:
                    seen_source_ids.add(payload.source_disclosure_id)
                seen_fallback_keys.add(fallback_key)
                continue

            disclosure = Disclosure(
                company_id=company.id,
                source_name=payload.source_name,
                disclosed_at=payload.disclosed_at,
                title=payload.title,
                normalized_title=payload.normalized_title,
                classification_reason=payload.classification_reason,
                category=payload.category,
                priority=payload.priority,
                source_url=payload.source_url,
                source_disclosure_id=payload.source_disclosure_id,
                is_new=True,
                is_analysis_target=payload.is_analysis_target,
            )
            self.session.add(disclosure)
            inserted += 1
            if payload.source_disclosure_id:
                seen_source_ids.add(payload.source_disclosure_id)
            seen_fallback_keys.add(fallback_key)

        self.session.flush()
        return {
            "inserted": inserted,
            "skipped": skipped,
            "skipped_inactive": skipped_inactive,
            "autocreated_companies": autocreated_companies,
        }
