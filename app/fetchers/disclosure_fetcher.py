from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


@dataclass
class DisclosureRecord:
    company_code: str
    source_name: str
    disclosed_at: datetime
    title: str
    source_url: str
    source_disclosure_id: str | None = None
    normalized_title: str | None = None


class DisclosureFetcher(Protocol):
    def fetch(self) -> list[DisclosureRecord]:
        ...


class DummyDisclosureFetcher:
    def __init__(self, input_path: str | Path) -> None:
        self.input_path = Path(input_path)

    def fetch(self) -> list[DisclosureRecord]:
        raw = json.loads(self.input_path.read_text(encoding="utf-8"))
        records: list[DisclosureRecord] = []
        for item in raw:
            records.append(
                DisclosureRecord(
                    company_code=str(item["company_code"]),
                    source_name=str(item.get("source_name", "dummy")),
                    disclosed_at=self._parse_datetime(str(item["disclosed_at"])),
                    title=str(item["title"]),
                    source_url=str(item["source_url"]),
                    source_disclosure_id=self._optional_string(item.get("source_disclosure_id")),
                    normalized_title=self._optional_string(item.get("normalized_title")),
                )
            )
        return records

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
