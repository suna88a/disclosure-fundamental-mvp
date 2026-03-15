from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.models.financial_report import FinancialReport


def calculate_progress_rate_operating_income(report: FinancialReport) -> Decimal | None:
    operating_income = report.operating_income
    forecast = report.company_forecast_operating_income
    if operating_income is None or forecast is None or forecast == 0:
        return None

    return ((operating_income / forecast) * Decimal("100")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
