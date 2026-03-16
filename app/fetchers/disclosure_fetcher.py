from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


JST = ZoneInfo("Asia/Tokyo")
COMPANY_CODE_PATTERN = re.compile(r"\b\d{4,6}\b")
TIME_PATTERN = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b")
DEFAULT_USER_AGENT = "disclosure-fundamental-mvp/1.0 (+https://www.jpx.co.jp/)"
logger = logging.getLogger(__name__)


@dataclass
class DisclosureRecord:
    company_code: str
    source_name: str
    disclosed_at: datetime
    title: str
    source_url: str
    company_name: str | None = None
    source_disclosure_id: str | None = None
    normalized_title: str | None = None


@dataclass(frozen=True)
class HtmlStructureDiagnostics:
    target_date: date
    url: str
    table_count: int
    row_count: int
    data_row_count: int
    extracted_count: int
    status: str
    reason: str


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
                    company_name=self._optional_string(item.get("company_name")),
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


class HttpJsonDisclosureFetcher:
    def __init__(
        self,
        url: str,
        *,
        source_name: str = "http-json",
        timeout: int = 30,
    ) -> None:
        self.url = url
        self.source_name = source_name
        self.timeout = timeout

    def fetch(self) -> list[DisclosureRecord]:
        response = requests.get(self.url, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        items = self._extract_items(payload)
        return [self._build_record(item) for item in items]

    def _extract_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [self._require_mapping(item) for item in payload]
        if isinstance(payload, dict):
            for key in ("items", "results", "data", "disclosures"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [self._require_mapping(item) for item in value]
        raise ValueError("Disclosure source must return a JSON array or an object with items/results/data/disclosures.")

    def _build_record(self, item: dict[str, Any]) -> DisclosureRecord:
        company_code = self._required_string(item, "company_code", "code", "ticker", "local_code")
        disclosed_at = self._parse_datetime(
            self._required_string(item, "disclosed_at", "disclosure_datetime", "published_at", "datetime")
        )
        title = self._required_string(item, "title")
        source_url = self._required_string(item, "source_url", "detail_url", "url")
        return DisclosureRecord(
            company_code=company_code,
            company_name=self._optional_string(item, "company_name", "name", "company", "company_title"),
            source_name=self._optional_string(item, "source_name") or self.source_name,
            disclosed_at=disclosed_at,
            title=title,
            source_url=source_url,
            source_disclosure_id=self._optional_string(item, "source_disclosure_id", "disclosure_id", "id"),
            normalized_title=self._optional_string(item, "normalized_title"),
        )

    @staticmethod
    def _require_mapping(item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("Each disclosure item must be a JSON object.")
        return item

    @staticmethod
    def _required_string(item: dict[str, Any], *keys: str) -> str:
        value = HttpJsonDisclosureFetcher._optional_string(item, *keys)
        if value is None:
            raise ValueError(f"Missing required disclosure field. Expected one of: {', '.join(keys)}")
        return value

    @staticmethod
    def _optional_string(item: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = item.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed


class JpxTdnetDisclosureFetcher:
    """Fetch disclosures from JPX Company Announcements Disclosure Service pages.

    The provider is fixed to JPX, while the actual list URL is supplied as a format
    template because the public JPX UI is JavaScript-driven. The template must accept
    `{date}` in YYYY-MM-DD format.
    """

    def __init__(
        self,
        url_template: str,
        *,
        target_date: date | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        timeout: int = 30,
        retry_count: int = 2,
        user_agent: str = DEFAULT_USER_AGENT,
        source_name: str = "jpx-tdnet",
        session: requests.Session | None = None,
    ) -> None:
        self.url_template = url_template
        self.timeout = timeout
        self.retry_count = retry_count
        self.user_agent = user_agent
        self.source_name = source_name
        self.target_date = target_date
        self.date_from = date_from
        self.date_to = date_to
        self.session = session or requests.Session()
        self._configure_session(self.session)
        self.last_diagnostics: list[HtmlStructureDiagnostics] = []

    def fetch(self) -> list[DisclosureRecord]:
        dates = list(self._build_dates())
        records: list[DisclosureRecord] = []
        seen_ids: set[str] = set()
        diagnostics: list[HtmlStructureDiagnostics] = []

        logger.info(
            "JPX fetch start source=%s dates=%s timeout=%s retry=%s",
            self.source_name,
            [value.isoformat() for value in dates],
            self.timeout,
            self.retry_count,
        )

        for target in dates:
            url = self.url_template.format(date=target.isoformat())
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            day_records, day_diagnostics = self._parse_html(response.text, base_url=url, target_date=target)
            diagnostics.append(day_diagnostics)

            logger.info(
                "JPX fetch date=%s status=%s tables=%s rows=%s data_rows=%s extracted=%s url=%s",
                target.isoformat(),
                day_diagnostics.status,
                day_diagnostics.table_count,
                day_diagnostics.row_count,
                day_diagnostics.data_row_count,
                day_diagnostics.extracted_count,
                url,
            )

            if day_diagnostics.status == "structure_anomaly_zero":
                raise ValueError(
                    f"JPX disclosure HTML structure anomaly for {target.isoformat()}: {day_diagnostics.reason}"
                )

            for record in day_records:
                dedupe_id = record.source_disclosure_id or f"{record.company_code}:{record.disclosed_at.isoformat()}:{record.title}"
                if dedupe_id in seen_ids:
                    continue
                seen_ids.add(dedupe_id)
                records.append(record)

        self.last_diagnostics = diagnostics
        logger.info("JPX fetch completed total_records=%s", len(records))
        return records

    def _configure_session(self, session: requests.Session) -> None:
        retry = Retry(
            total=self.retry_count,
            connect=self.retry_count,
            read=self.retry_count,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"User-Agent": self.user_agent})

    def _build_dates(self) -> list[date]:
        if self.target_date and (self.date_from or self.date_to):
            raise ValueError("Use either target_date or date_from/date_to, not both.")
        if self.target_date:
            return [self.target_date]
        if self.date_from or self.date_to:
            if not self.date_from or not self.date_to:
                raise ValueError("Both date_from and date_to are required for range fetch.")
            if self.date_from > self.date_to:
                raise ValueError("date_from must be earlier than or equal to date_to.")
            current = self.date_from
            dates: list[date] = []
            while current <= self.date_to:
                dates.append(current)
                current += timedelta(days=1)
            return dates
        return [datetime.now(JST).date()]

    def _parse_html(self, html: str, *, base_url: str, target_date: date) -> tuple[list[DisclosureRecord], HtmlStructureDiagnostics]:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.select("table")
        rows = soup.select("table tr")
        records: list[DisclosureRecord] = []
        data_row_count = 0

        for row in rows:
            tds = row.find_all("td")
            if len(tds) < 3:
                continue
            data_row_count += 1
            texts = [self._clean_text(cell.get_text(" ", strip=True)) for cell in tds]
            code_index = self._find_company_code_index(texts)
            if code_index is None:
                continue
            company_code = self._extract_company_code(texts[code_index])
            if company_code is None:
                continue
            disclosed_at = self._extract_disclosed_at(texts, target_date)
            company_name = texts[code_index + 1] if code_index + 1 < len(texts) else None
            anchor = row.find("a", href=True)
            source_url = urljoin(base_url, anchor["href"]) if anchor else base_url
            title = self._extract_title(texts, code_index, company_name, anchor)
            if not title:
                continue
            source_disclosure_id = self._build_source_disclosure_id(source_url)
            records.append(
                DisclosureRecord(
                    company_code=company_code,
                    company_name=company_name,
                    source_name=self.source_name,
                    disclosed_at=disclosed_at,
                    title=title,
                    source_url=source_url,
                    source_disclosure_id=source_disclosure_id,
                )
            )

        diagnostics = self._build_diagnostics(
            target_date=target_date,
            url=base_url,
            table_count=len(tables),
            row_count=len(rows),
            data_row_count=data_row_count,
            extracted_count=len(records),
        )
        return records, diagnostics

    @staticmethod
    def _build_diagnostics(
        *,
        target_date: date,
        url: str,
        table_count: int,
        row_count: int,
        data_row_count: int,
        extracted_count: int,
    ) -> HtmlStructureDiagnostics:
        if table_count == 0:
            return HtmlStructureDiagnostics(
                target_date=target_date,
                url=url,
                table_count=table_count,
                row_count=row_count,
                data_row_count=data_row_count,
                extracted_count=extracted_count,
                status="structure_anomaly_zero",
                reason="no_table_found",
            )
        if data_row_count == 0:
            return HtmlStructureDiagnostics(
                target_date=target_date,
                url=url,
                table_count=table_count,
                row_count=row_count,
                data_row_count=data_row_count,
                extracted_count=extracted_count,
                status="normal_zero",
                reason="no_data_rows_found",
            )
        if extracted_count == 0:
            return HtmlStructureDiagnostics(
                target_date=target_date,
                url=url,
                table_count=table_count,
                row_count=row_count,
                data_row_count=data_row_count,
                extracted_count=extracted_count,
                status="structure_anomaly_zero",
                reason="data_rows_present_but_no_records_extracted",
            )
        return HtmlStructureDiagnostics(
            target_date=target_date,
            url=url,
            table_count=table_count,
            row_count=row_count,
            data_row_count=data_row_count,
            extracted_count=extracted_count,
            status="ok",
            reason="records_extracted",
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _find_company_code_index(texts: list[str]) -> int | None:
        for index, text in enumerate(texts):
            if COMPANY_CODE_PATTERN.search(text):
                return index
        return None

    @staticmethod
    def _extract_company_code(text: str) -> str | None:
        match = COMPANY_CODE_PATTERN.search(text)
        return match.group(0) if match else None

    @staticmethod
    def _extract_disclosed_at(texts: list[str], target_date: date) -> datetime:
        for text in texts:
            match = TIME_PATTERN.search(text)
            if match:
                parts = match.group(1).split(":")
                hour = int(parts[0])
                minute = int(parts[1])
                second = int(parts[2]) if len(parts) > 2 else 0
                return datetime(target_date.year, target_date.month, target_date.day, hour, minute, second, tzinfo=JST)
        return datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=JST)

    @staticmethod
    def _extract_title(texts: list[str], code_index: int, company_name: str | None, anchor) -> str:
        if anchor:
            anchor_text = JpxTdnetDisclosureFetcher._clean_text(anchor.get_text(" ", strip=True))
            if anchor_text and anchor_text != company_name:
                return anchor_text
        for idx, text in enumerate(texts):
            if idx <= code_index:
                continue
            if company_name and text == company_name:
                continue
            if TIME_PATTERN.search(text):
                continue
            if text:
                return text
        return ""

    @staticmethod
    def _build_source_disclosure_id(source_url: str) -> str:
        parsed = urlsplit(source_url)
        normalized_query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            query=normalized_query,
            fragment="",
        )
        return urlunsplit(normalized)
