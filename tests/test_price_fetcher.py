from datetime import date, datetime
from decimal import Decimal

from app.fetchers.price_fetcher import YFinancePriceFetcher


class TestYFinancePriceFetcher:
    def test_build_symbol_for_japan_equity_code(self) -> None:
        fetcher = YFinancePriceFetcher()

        assert fetcher.build_symbol("7203") == "7203.T"

    def test_fetch_range_returns_normalized_records(self, monkeypatch) -> None:
        fetcher = YFinancePriceFetcher()

        def fake_fetch_history_rows(symbol: str, start_date: date, end_date: date):
            assert symbol == "7203.T"
            return [
                {
                    "trade_date": date(2026, 3, 18),
                    "open": "1000.5",
                    "high": "1010.0",
                    "low": "995.0",
                    "close": "1005.0",
                    "adj_close": "1004.5",
                    "volume": "123456",
                }
            ]

        monkeypatch.setattr(fetcher, "_fetch_history_rows", fake_fetch_history_rows)

        result = fetcher.fetch_range("7203", date(2026, 3, 18), date(2026, 3, 18))

        assert len(result) == 1
        assert result[0].code == "7203"
        assert result[0].source == "yfinance"
        assert result[0].source_symbol == "7203.T"
        assert result[0].trade_date == date(2026, 3, 18)
        assert result[0].close == Decimal("1005.0")
        assert result[0].adj_close == Decimal("1004.5")
        assert result[0].volume == 123456

    def test_fetch_daily_returns_none_for_empty_data(self, monkeypatch) -> None:
        fetcher = YFinancePriceFetcher()
        monkeypatch.setattr(fetcher, "_fetch_history_rows", lambda symbol, start_date, end_date: [])

        result = fetcher.fetch_daily("7203", date(2026, 3, 18))

        assert result is None
