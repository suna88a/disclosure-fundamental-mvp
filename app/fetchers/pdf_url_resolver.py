from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.models.disclosure import Disclosure


@dataclass(frozen=True)
class PdfResolutionResult:
    source_url: str | None
    resolution_reason: str


class PdfUrlResolver(Protocol):
    def resolve(self, disclosure: Disclosure) -> PdfResolutionResult:
        ...


class DummyPdfUrlResolver:
    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        self._manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def resolve(self, disclosure: Disclosure) -> PdfResolutionResult:
        entries = self._manifest.get("items", [])
        for item in entries:
            if item.get("source_disclosure_id") and item["source_disclosure_id"] == disclosure.source_disclosure_id:
                return PdfResolutionResult(
                    source_url=item.get("pdf_url"),
                    resolution_reason=f"Resolved by source_disclosure_id from manifest {self.manifest_path.name}.",
                )
            if item.get("title") and item["title"] == disclosure.title:
                return PdfResolutionResult(
                    source_url=item.get("pdf_url"),
                    resolution_reason=f"Resolved by title from manifest {self.manifest_path.name}.",
                )

        return PdfResolutionResult(
            source_url=None,
            resolution_reason=f"No PDF URL found in manifest {self.manifest_path.name}.",
        )
