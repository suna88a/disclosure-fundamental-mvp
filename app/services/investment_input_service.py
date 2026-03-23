from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.disclosure import Disclosure
from app.repositories.financial_report_repository import FinancialReportRepository
from app.repositories.revision_repository import RevisionRepository
from app.services.reference_price import resolve_reference_price


@dataclass(frozen=True)
class InvestmentMetricInputs:
    code: str | None
    disclosure_date: date
    reference_trade_date: date | None
    reference_close: Decimal | None
    reference_price_source: str | None
    reference_price_symbol: str | None
    eps: Decimal | None
    eps_source: str | None
    eps_basis: str
    annual_dps: Decimal | None
    annual_dps_source: str
    warnings: tuple[str, ...]


def get_disclosure_investment_metric_inputs(
    session: Session, disclosure: Disclosure
) -> InvestmentMetricInputs:
    code = disclosure.company.code if disclosure.company is not None else None
    reference_price = resolve_reference_price(session, code, disclosure.disclosed_at) if code else None
    financial_report = FinancialReportRepository(session).get_by_disclosure_id(disclosure.id)
    dividend_revision = RevisionRepository(session).get_dividend_revision(disclosure.id)
    eps, eps_source, eps_basis = _resolve_eps(financial_report)
    annual_dps, annual_dps_source = _resolve_annual_dps(dividend_revision)

    warnings: list[str] = []
    if code is None or not str(code).strip():
        warnings.append("company_code_missing")
    if reference_price is None:
        warnings.append("reference_price_missing")
    if eps is None:
        warnings.append("eps_missing")
    if eps_basis == "actual":
        warnings.append("eps_basis_actual")
    if annual_dps is None:
        warnings.append("annual_dps_missing")
    if annual_dps_source == "partial":
        warnings.append("annual_dps_partial")

    return InvestmentMetricInputs(
        code=code,
        disclosure_date=disclosure.disclosed_at.date(),
        reference_trade_date=reference_price.reference_trade_date if reference_price else None,
        reference_close=reference_price.close if reference_price else None,
        reference_price_source=reference_price.source if reference_price else None,
        reference_price_symbol=reference_price.source_symbol if reference_price else None,
        eps=eps,
        eps_source=eps_source,
        eps_basis=eps_basis,
        annual_dps=annual_dps,
        annual_dps_source=annual_dps_source,
        warnings=tuple(warnings),
    )


def _resolve_eps(financial_report: object | None) -> tuple[Decimal | None, str | None, str]:
    if financial_report is None:
        return None, None, "unknown"
    company_forecast_eps = getattr(financial_report, "company_forecast_eps", None)
    if company_forecast_eps is not None:
        return company_forecast_eps, "company_forecast_eps", "forecast"
    eps = getattr(financial_report, "eps", None)
    if eps is not None:
        return eps, "eps", "actual"
    return None, None, "unknown"


def _resolve_annual_dps(dividend_revision: object | None) -> tuple[Decimal | None, str]:
    if dividend_revision is None:
        return None, "missing"

    annual_after = getattr(dividend_revision, "annual_dividend_after", None)
    if annual_after is not None:
        return annual_after, "annual_dividend_after"

    interim_after = getattr(dividend_revision, "interim_dividend_after", None)
    year_end_after = getattr(dividend_revision, "year_end_dividend_after", None)
    if interim_after is not None and year_end_after is not None:
        return interim_after + year_end_after, "interim_plus_year_end"
    if year_end_after is not None or interim_after is not None:
        return year_end_after if year_end_after is not None else interim_after, "partial"
    return None, "missing"
