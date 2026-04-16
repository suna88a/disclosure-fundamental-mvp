import sys

from app.config import get_settings
from scripts import run_disclosure_fetch, run_pipeline


def test_run_disclosure_fetch_parse_args_reads_jpx_settings(monkeypatch) -> None:
    monkeypatch.setenv("JPX_DISCLOSURE_URL_TEMPLATE", "https://www.release.tdnet.info/inbs/I_list_001_{date_yyyymmdd}.html")
    monkeypatch.delenv("DISCLOSURE_SOURCE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_disclosure_fetch.py"])
    get_settings.cache_clear()

    args = run_disclosure_fetch.parse_args()

    assert args.source == "jpx-tdnet"
    assert args.url_template == "https://www.release.tdnet.info/inbs/I_list_001_{date_yyyymmdd}.html"
    get_settings.cache_clear()


def test_run_disclosure_fetch_parse_args_reads_http_json_settings(monkeypatch) -> None:
    monkeypatch.delenv("JPX_DISCLOSURE_URL_TEMPLATE", raising=False)
    monkeypatch.setenv("DISCLOSURE_SOURCE_URL", "https://example.com/disclosures.json")
    monkeypatch.setattr(sys, "argv", ["run_disclosure_fetch.py"])
    get_settings.cache_clear()

    args = run_disclosure_fetch.parse_args()

    assert args.source == "http-json"
    assert args.url == "https://example.com/disclosures.json"
    get_settings.cache_clear()


def test_run_pipeline_parse_args_reads_jpx_settings(monkeypatch) -> None:
    monkeypatch.setenv("JPX_DISCLOSURE_URL_TEMPLATE", "https://www.release.tdnet.info/inbs/I_list_001_{date_yyyymmdd}.html")
    monkeypatch.delenv("DISCLOSURE_SOURCE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py"])
    get_settings.cache_clear()

    args = run_pipeline.parse_args()

    assert args.disclosure_source == "jpx-tdnet"
    assert args.disclosure_url_template == "https://www.release.tdnet.info/inbs/I_list_001_{date_yyyymmdd}.html"
    get_settings.cache_clear()
