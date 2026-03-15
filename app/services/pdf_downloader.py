from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


@dataclass(frozen=True)
class DownloadedPdf:
    file_path: str
    file_hash: str


class PdfDownloader:
    def __init__(self, storage_dir: str | Path) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def download(self, source_url: str, disclosure_id: int) -> DownloadedPdf:
        content = self._read_bytes(source_url)
        file_hash = hashlib.sha256(content).hexdigest()
        destination = self.storage_dir / f"{disclosure_id}_{file_hash[:16]}.pdf"
        if not destination.exists():
            destination.write_bytes(content)
        return DownloadedPdf(file_path=str(destination), file_hash=file_hash)

    @staticmethod
    def _read_bytes(source_url: str) -> bytes:
        parsed = urlparse(source_url)
        if parsed.scheme in {"", "file"}:
            if parsed.scheme == "file":
                source_path = Path(parsed.path.lstrip("/"))
            else:
                source_path = Path(source_url)
            return source_path.read_bytes()

        with urlopen(source_url, timeout=30) as response:
            return response.read()
