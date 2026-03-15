from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from app.models.enums import (
    CumulativeType,
    PdfParseErrorCode,
    PeriodType,
    StatementScope,
)
from app.models.pdf_file import PdfFile


SUPPORTED_PDF_FORMATS = (
    "dummy.tabular_summary_v1",
    "dummy.tabular_summary_v2",
    "dummy.tabular_summary_v3",
    "dummy.tabular_summary_v4",
)


@dataclass(frozen=True)
class ParsedFinancialReport:
    supported: bool
    support_reason: str
    error_code: PdfParseErrorCode | None = None
    accounting_standard: str | None = None
    period_type: PeriodType | None = None
    statement_scope: StatementScope | None = None
    cumulative_type: CumulativeType | None = None
    sales: Decimal | None = None
    operating_income: Decimal | None = None
    ordinary_income: Decimal | None = None
    net_income: Decimal | None = None
    eps: Decimal | None = None
    company_forecast_sales: Decimal | None = None
    company_forecast_operating_income: Decimal | None = None
    company_forecast_ordinary_income: Decimal | None = None
    company_forecast_net_income: Decimal | None = None
    company_forecast_eps: Decimal | None = None
    extraction_confidence: Decimal | None = None
    extraction_version: str = "v1"


class FinancialReportParser(Protocol):
    def parse(self, pdf_file: PdfFile) -> ParsedFinancialReport:
        ...


class DummyFinancialReportParser:
    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def parse(self, pdf_file: PdfFile) -> ParsedFinancialReport:
        entry = self._find_entry(pdf_file)
        if entry is None:
            return ParsedFinancialReport(
                supported=False,
                support_reason=f"No parser manifest entry found in {self.manifest_path.name}.",
                error_code=PdfParseErrorCode.MANIFEST_ENTRY_MISSING,
            )

        format_name = str(entry.get("format", ""))
        if format_name not in SUPPORTED_PDF_FORMATS:
            return ParsedFinancialReport(
                supported=False,
                support_reason=f"Unsupported format={format_name}. Supported={SUPPORTED_PDF_FORMATS}.",
                error_code=PdfParseErrorCode.UNSUPPORTED_FORMAT,
            )

        payload = entry.get("financial_report")
        if not isinstance(payload, dict):
            return ParsedFinancialReport(
                supported=False,
                support_reason=f"Missing financial_report payload in {self.manifest_path.name}.",
                error_code=PdfParseErrorCode.PARSE_TARGET_MISSING,
            )

        if format_name == "dummy.tabular_summary_v1":
            parsed = _parse_v1_payload(payload)
        elif format_name == "dummy.tabular_summary_v2":
            parsed = _parse_v2_payload(payload)
        elif format_name == "dummy.tabular_summary_v3":
            parsed = _parse_v3_payload(payload)
        elif format_name == "dummy.tabular_summary_v4":
            parsed = _parse_v4_payload(payload)
        else:
            return ParsedFinancialReport(
                supported=False,
                support_reason=f"Unsupported format={format_name}. Supported={SUPPORTED_PDF_FORMATS}.",
                error_code=PdfParseErrorCode.UNSUPPORTED_FORMAT,
            )

        return _validate_parsed_report(parsed)

    def _find_entry(self, pdf_file: PdfFile) -> dict[str, object] | None:
        disclosure_source_id = pdf_file.disclosure.source_disclosure_id
        if disclosure_source_id:
            for item in self.manifest.get("items", []):
                if item.get("source_disclosure_id") == disclosure_source_id:
                    return item
            return None

        for item in self.manifest.get("items", []):
            if item.get("pdf_source_url") and pdf_file.source_url:
                if item["pdf_source_url"] == pdf_file.source_url:
                    return item
        return None


def _parse_v1_payload(payload: dict[str, object]) -> ParsedFinancialReport:
    return ParsedFinancialReport(
        supported=True,
        support_reason="Supported by dummy.tabular_summary_v1.",
        accounting_standard=_optional_str(payload.get("accounting_standard")),
        period_type=_to_period_type(payload.get("period_type")),
        statement_scope=_to_statement_scope(payload.get("statement_scope")),
        cumulative_type=_to_cumulative_type(payload.get("cumulative_type")),
        sales=_to_decimal(payload.get("sales")),
        operating_income=_to_decimal(payload.get("operating_income")),
        ordinary_income=_to_decimal(payload.get("ordinary_income")),
        net_income=_to_decimal(payload.get("net_income")),
        eps=_to_decimal(payload.get("eps")),
        company_forecast_sales=_to_decimal(payload.get("company_forecast_sales")),
        company_forecast_operating_income=_to_decimal(payload.get("company_forecast_operating_income")),
        company_forecast_ordinary_income=_to_decimal(payload.get("company_forecast_ordinary_income")),
        company_forecast_net_income=_to_decimal(payload.get("company_forecast_net_income")),
        company_forecast_eps=_to_decimal(payload.get("company_forecast_eps")),
        extraction_confidence=_to_decimal(payload.get("extraction_confidence")),
        extraction_version=_optional_str(payload.get("extraction_version")) or "v1",
    )


def _parse_v2_payload(payload: dict[str, object]) -> ParsedFinancialReport:
    period = payload.get("period") if isinstance(payload.get("period"), dict) else {}
    actual = payload.get("actual") if isinstance(payload.get("actual"), dict) else {}
    forecast = payload.get("forecast") if isinstance(payload.get("forecast"), dict) else {}

    return ParsedFinancialReport(
        supported=True,
        support_reason="Supported by dummy.tabular_summary_v2.",
        accounting_standard=_optional_str(payload.get("accounting_standard")),
        period_type=_to_period_type(period.get("type")),
        statement_scope=_to_statement_scope(period.get("scope")),
        cumulative_type=_to_cumulative_type(period.get("cumulative_type")),
        sales=_to_decimal(actual.get("sales")),
        operating_income=_to_decimal(actual.get("operating_income")),
        ordinary_income=_to_decimal(actual.get("ordinary_income")),
        net_income=_to_decimal(actual.get("net_income")),
        eps=_to_decimal(actual.get("eps")),
        company_forecast_sales=_to_decimal(forecast.get("sales")),
        company_forecast_operating_income=_to_decimal(forecast.get("operating_income")),
        company_forecast_ordinary_income=_to_decimal(forecast.get("ordinary_income")),
        company_forecast_net_income=_to_decimal(forecast.get("net_income")),
        company_forecast_eps=_to_decimal(forecast.get("eps")),
        extraction_confidence=_to_decimal(payload.get("extraction_confidence")),
        extraction_version=_optional_str(payload.get("extraction_version")) or "v2",
    )


def _parse_v3_payload(payload: dict[str, object]) -> ParsedFinancialReport:
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    actual = payload.get("actual_results") if isinstance(payload.get("actual_results"), dict) else {}
    forecast = payload.get("company_forecast") if isinstance(payload.get("company_forecast"), dict) else {}

    return ParsedFinancialReport(
        supported=True,
        support_reason="Supported by dummy.tabular_summary_v3.",
        accounting_standard=_optional_str(payload.get("accounting_standard")) or _optional_str(header.get("accounting_standard")),
        period_type=_to_period_type(header.get("period_type")),
        statement_scope=_to_statement_scope(header.get("statement_scope")),
        cumulative_type=_to_cumulative_type(header.get("cumulative_type")),
        sales=_to_decimal(actual.get("revenue") or actual.get("sales")),
        operating_income=_to_decimal(actual.get("operating_income") or actual.get("op_income")),
        ordinary_income=_to_decimal(actual.get("ordinary_income") or actual.get("recurring_income")),
        net_income=_to_decimal(actual.get("net_income") or actual.get("profit_attributable_to_owners")),
        eps=_to_decimal(actual.get("eps")),
        company_forecast_sales=_to_decimal(forecast.get("revenue") or forecast.get("sales")),
        company_forecast_operating_income=_to_decimal(forecast.get("operating_income") or forecast.get("op_income")),
        company_forecast_ordinary_income=_to_decimal(forecast.get("ordinary_income") or forecast.get("recurring_income")),
        company_forecast_net_income=_to_decimal(forecast.get("net_income") or forecast.get("profit_attributable_to_owners")),
        company_forecast_eps=_to_decimal(forecast.get("eps")),
        extraction_confidence=_to_decimal(payload.get("extraction_confidence")),
        extraction_version=_optional_str(payload.get("extraction_version")) or "v3",
    )


def _parse_v4_payload(payload: dict[str, object]) -> ParsedFinancialReport:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    results = payload.get("results") if isinstance(payload.get("results"), dict) else {}
    outlook = payload.get("outlook") if isinstance(payload.get("outlook"), dict) else {}

    return ParsedFinancialReport(
        supported=True,
        support_reason="Supported by dummy.tabular_summary_v4.",
        accounting_standard=_optional_str(meta.get("gaap")) or _optional_str(payload.get("accounting_standard")),
        period_type=_to_period_type(meta.get("period")),
        statement_scope=_to_statement_scope(meta.get("scope_type")),
        cumulative_type=_to_cumulative_type(meta.get("aggregation")),
        sales=_to_decimal(results.get("net_sales") or results.get("sales")),
        operating_income=_to_decimal(results.get("business_profit") or results.get("operating_income")),
        ordinary_income=_to_decimal(results.get("ordinary_profit") or results.get("ordinary_income")),
        net_income=_to_decimal(results.get("profit") or results.get("net_income")),
        eps=_to_decimal(results.get("eps_value") or results.get("eps")),
        company_forecast_sales=_to_decimal(outlook.get("net_sales") or outlook.get("sales")),
        company_forecast_operating_income=_to_decimal(outlook.get("business_profit") or outlook.get("operating_income")),
        company_forecast_ordinary_income=_to_decimal(outlook.get("ordinary_profit") or outlook.get("ordinary_income")),
        company_forecast_net_income=_to_decimal(outlook.get("profit") or outlook.get("net_income")),
        company_forecast_eps=_to_decimal(outlook.get("eps_value") or outlook.get("eps")),
        extraction_confidence=_to_decimal(payload.get("extraction_confidence")),
        extraction_version=_optional_str(payload.get("extraction_version")) or "v4",
    )


def _to_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_period_type(value: object) -> PeriodType | None:
    text = _optional_str(value)
    return PeriodType(text) if text else None


def _to_statement_scope(value: object) -> StatementScope | None:
    text = _optional_str(value)
    return StatementScope(text) if text else None


def _to_cumulative_type(value: object) -> CumulativeType | None:
    text = _optional_str(value)
    return CumulativeType(text) if text else None


def _validate_parsed_report(parsed: ParsedFinancialReport) -> ParsedFinancialReport:
    if parsed.period_type is None:
        return ParsedFinancialReport(
            supported=False,
            support_reason="Missing period_type in financial_report payload.",
            error_code=PdfParseErrorCode.PERIOD_DETECTION_FAILED,
        )
    if parsed.statement_scope is None:
        return ParsedFinancialReport(
            supported=False,
            support_reason="Missing statement_scope in financial_report payload.",
            error_code=PdfParseErrorCode.SCOPE_DETECTION_FAILED,
        )
    if parsed.cumulative_type is None:
        return ParsedFinancialReport(
            supported=False,
            support_reason="Missing cumulative_type in financial_report payload.",
            error_code=PdfParseErrorCode.CUMULATIVE_TYPE_DETECTION_FAILED,
        )
    if parsed.company_forecast_operating_income is None:
        return ParsedFinancialReport(
            supported=False,
            support_reason="Missing company_forecast_operating_income in financial_report payload.",
            error_code=PdfParseErrorCode.FORECAST_SECTION_MISSING,
        )
    if parsed.operating_income is None:
        return ParsedFinancialReport(
            supported=False,
            support_reason="Missing operating_income in financial_report payload.",
            error_code=PdfParseErrorCode.VALUE_NOT_FOUND,
        )
    return parsed
