from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from app.models.disclosure import Disclosure
from app.models.enums import RevisionDirection


@dataclass(frozen=True)
class GuidanceRevisionPayload:
    revised_sales_before: Decimal | None = None
    revised_sales_after: Decimal | None = None
    revised_operating_income_before: Decimal | None = None
    revised_operating_income_after: Decimal | None = None
    revised_ordinary_income_before: Decimal | None = None
    revised_ordinary_income_after: Decimal | None = None
    revised_net_income_before: Decimal | None = None
    revised_net_income_after: Decimal | None = None
    revised_eps_before: Decimal | None = None
    revised_eps_after: Decimal | None = None
    revision_rate_operating_income: Decimal | None = None
    revision_direction: RevisionDirection | None = None


@dataclass(frozen=True)
class DividendRevisionPayload:
    interim_dividend_before: Decimal | None = None
    interim_dividend_after: Decimal | None = None
    year_end_dividend_before: Decimal | None = None
    year_end_dividend_after: Decimal | None = None
    annual_dividend_before: Decimal | None = None
    annual_dividend_after: Decimal | None = None
    revision_direction: RevisionDirection | None = None


@dataclass(frozen=True)
class RevisionExtractionResult:
    guidance_revision: GuidanceRevisionPayload | None
    dividend_revision: DividendRevisionPayload | None
    extraction_reason: str


class RevisionExtractor(Protocol):
    def extract(self, disclosure: Disclosure) -> RevisionExtractionResult:
        ...


class DummyRevisionExtractor:
    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def extract(self, disclosure: Disclosure) -> RevisionExtractionResult:
        for item in self.manifest.get("items", []):
            if item.get("source_disclosure_id") and item["source_disclosure_id"] == disclosure.source_disclosure_id:
                return self._build_result(item, "source_disclosure_id")
            if item.get("title") and item["title"] == disclosure.title:
                return self._build_result(item, "title")

        return RevisionExtractionResult(
            guidance_revision=None,
            dividend_revision=None,
            extraction_reason=f"No revision payload found in {self.manifest_path.name}.",
        )

    def _build_result(self, item: dict[str, object], matched_by: str) -> RevisionExtractionResult:
        return RevisionExtractionResult(
            guidance_revision=self._build_guidance_payload(item.get("guidance_revision")),
            dividend_revision=self._build_dividend_payload(item.get("dividend_revision")),
            extraction_reason=f"Matched revision payload by {matched_by} in {self.manifest_path.name}.",
        )

    def _build_guidance_payload(self, payload: object) -> GuidanceRevisionPayload | None:
        if not isinstance(payload, dict):
            return None
        return GuidanceRevisionPayload(
            revised_sales_before=_to_decimal(payload.get("revised_sales_before")),
            revised_sales_after=_to_decimal(payload.get("revised_sales_after")),
            revised_operating_income_before=_to_decimal(payload.get("revised_operating_income_before")),
            revised_operating_income_after=_to_decimal(payload.get("revised_operating_income_after")),
            revised_ordinary_income_before=_to_decimal(payload.get("revised_ordinary_income_before")),
            revised_ordinary_income_after=_to_decimal(payload.get("revised_ordinary_income_after")),
            revised_net_income_before=_to_decimal(payload.get("revised_net_income_before")),
            revised_net_income_after=_to_decimal(payload.get("revised_net_income_after")),
            revised_eps_before=_to_decimal(payload.get("revised_eps_before")),
            revised_eps_after=_to_decimal(payload.get("revised_eps_after")),
            revision_rate_operating_income=_to_decimal(payload.get("revision_rate_operating_income")),
            revision_direction=_to_revision_direction(payload.get("revision_direction")),
        )

    def _build_dividend_payload(self, payload: object) -> DividendRevisionPayload | None:
        if not isinstance(payload, dict):
            return None
        return DividendRevisionPayload(
            interim_dividend_before=_to_decimal(payload.get("interim_dividend_before")),
            interim_dividend_after=_to_decimal(payload.get("interim_dividend_after")),
            year_end_dividend_before=_to_decimal(payload.get("year_end_dividend_before")),
            year_end_dividend_after=_to_decimal(payload.get("year_end_dividend_after")),
            annual_dividend_before=_to_decimal(payload.get("annual_dividend_before")),
            annual_dividend_after=_to_decimal(payload.get("annual_dividend_after")),
            revision_direction=_to_revision_direction(payload.get("revision_direction")),
        )


def _to_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _to_revision_direction(value: object) -> RevisionDirection | None:
    if value is None or value == "":
        return None
    return RevisionDirection(str(value))
