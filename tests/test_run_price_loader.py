import argparse
import builtins
from datetime import date

from scripts import run_price_loader


class _DummyContext:
    def __init__(self) -> None:
        self.session = object()
        self.processed_count = None

    def set_processed_count(self, count: int) -> None:
        self.processed_count = count


def _run_main(monkeypatch, args: argparse.Namespace):
    captured: dict[str, object] = {}
    context = _DummyContext()

    monkeypatch.setattr(run_price_loader, "parse_args", lambda: args)
    monkeypatch.setattr(run_price_loader, "YFinancePriceFetcher", lambda: "fake-fetcher")

    def fake_load_prices(session, **kwargs):
        captured["session"] = session
        captured.update(kwargs)
        return {
            "fetched": 3,
            "inserted": 2,
            "updated": 0,
            "skipped": 1,
            "empty_codes": 0,
            "failed": 0,
            "dry_run": int(kwargs.get("dry_run", False)),
            "processed": len(kwargs["codes"]),
        }

    def fake_run_job(job_name, job_callable):
        captured["job_name"] = job_name
        result = job_callable(context)
        captured["processed_count"] = context.processed_count
        return result

    monkeypatch.setattr(run_price_loader, "load_prices", fake_load_prices)
    monkeypatch.setattr(run_price_loader, "run_job", fake_run_job)
    monkeypatch.setattr(builtins, "print", lambda result: captured.setdefault("printed", result))

    run_price_loader.main()
    return captured


def test_run_price_loader_main_supports_code_and_date(monkeypatch) -> None:
    captured = _run_main(
        monkeypatch,
        argparse.Namespace(
            source="yfinance",
            code=["7203"],
            target_date=date(2026, 3, 19),
            start_date=None,
            end_date=None,
            dry_run=False,
            force=False,
        ),
    )

    assert captured["job_name"] == "load_price_daily"
    assert captured["fetcher"] == "fake-fetcher"
    assert captured["codes"] == ["7203"]
    assert captured["start_date"] == date(2026, 3, 19)
    assert captured["end_date"] == date(2026, 3, 19)
    assert captured["dry_run"] is False
    assert captured["force"] is False
    assert captured["processed_count"] == 3


def test_run_price_loader_main_supports_start_end_date(monkeypatch) -> None:
    captured = _run_main(
        monkeypatch,
        argparse.Namespace(
            source="yfinance",
            code=["7203"],
            target_date=None,
            start_date=date(2026, 3, 17),
            end_date=date(2026, 3, 21),
            dry_run=False,
            force=False,
        ),
    )

    assert captured["start_date"] == date(2026, 3, 17)
    assert captured["end_date"] == date(2026, 3, 21)


def test_run_price_loader_main_supports_dry_run(monkeypatch) -> None:
    captured = _run_main(
        monkeypatch,
        argparse.Namespace(
            source="yfinance",
            code=["7203"],
            target_date=date(2026, 3, 19),
            start_date=None,
            end_date=None,
            dry_run=True,
            force=False,
        ),
    )

    assert captured["dry_run"] is True
    assert captured["printed"]["dry_run"] == 1


def test_run_price_loader_main_supports_force(monkeypatch) -> None:
    captured = _run_main(
        monkeypatch,
        argparse.Namespace(
            source="yfinance",
            code=["7203"],
            target_date=date(2026, 3, 19),
            start_date=None,
            end_date=None,
            dry_run=False,
            force=True,
        ),
    )

    assert captured["force"] is True
