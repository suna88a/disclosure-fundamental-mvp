from __future__ import annotations

from dataclasses import asdict

from app.fetchers.financial_report_parser import ParsedFinancialReport


def build_financial_report_payload(
    parsed: ParsedFinancialReport,
    pdf_file_id: int,
) -> dict[str, object]:
    if not parsed.supported:
        raise ValueError("Cannot build financial report payload from unsupported parser result.")

    payload = asdict(parsed)
    payload.pop("supported", None)
    payload.pop("support_reason", None)
    payload["pdf_file_id"] = pdf_file_id
    return payload
