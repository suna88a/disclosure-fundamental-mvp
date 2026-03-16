from datetime import date, datetime

import pytest
import requests

from app.fetchers.disclosure_fetcher import DEFAULT_USER_AGENT, HttpJsonDisclosureFetcher, JpxTdnetDisclosureFetcher
from app.repositories.disclosure_repository import DisclosureCreateInput, DisclosureRepository
from app.db import Base
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


class DummyResponse:
    def __init__(self, payload=None, text: str = ""):
        self._payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, responder):
        self._responder = responder
        self.headers = {}
        self.mounted = {}

    def get(self, url: str, timeout: int):
        return self._responder(url, timeout)

    def mount(self, prefix: str, adapter) -> None:
        self.mounted[prefix] = adapter



def _build_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()



def test_http_json_disclosure_fetcher_reads_items_payload(monkeypatch) -> None:
    payload = {
        "items": [
            {
                "company_code": "7203",
                "company_name": "Toyota Motor Corporation",
                "disclosed_at": "2026-03-16T15:00:00+09:00",
                "title": "Summary of Consolidated Financial Results",
                "source_url": "https://example.com/disclosures/7203-001",
                "source_disclosure_id": "7203-001",
            }
        ]
    }

    def fake_get(url: str, timeout: int):
        assert url == "https://example.com/feed.json"
        assert timeout == 15
        return DummyResponse(payload=payload)

    monkeypatch.setattr("app.fetchers.disclosure_fetcher.requests.get", fake_get)

    fetcher = HttpJsonDisclosureFetcher("https://example.com/feed.json", timeout=15)
    records = fetcher.fetch()

    assert len(records) == 1
    assert records[0].company_code == "7203"
    assert records[0].company_name == "Toyota Motor Corporation"
    assert records[0].source_url == "https://example.com/disclosures/7203-001"
    assert records[0].disclosed_at == datetime.fromisoformat("2026-03-16T15:00:00+09:00")



def test_http_json_disclosure_fetcher_rejects_missing_required_fields(monkeypatch) -> None:
    payload = [{"title": "Missing code and url"}]

    def fake_get(url: str, timeout: int):
        return DummyResponse(payload=payload)

    monkeypatch.setattr("app.fetchers.disclosure_fetcher.requests.get", fake_get)

    fetcher = HttpJsonDisclosureFetcher("https://example.com/feed.json")

    with pytest.raises(ValueError):
        fetcher.fetch()



def test_jpx_tdnet_fetcher_reads_single_day_html(monkeypatch) -> None:
    html = """
    <html><body>
      <table>
        <tr><th>時刻</th><th>コード</th><th>会社名</th><th>表題</th></tr>
        <tr>
          <td>15:00</td>
          <td>7203</td>
          <td>トヨタ自動車</td>
          <td><a href="/detail/7203-001.pdf?b=2&a=1#fragment">決算短信</a></td>
        </tr>
      </table>
    </body></html>
    """

    def fake_get(url: str, timeout: int):
        assert url == "https://example.com/jpx?date=2026-03-16"
        return DummyResponse(text=html)

    fetcher = JpxTdnetDisclosureFetcher(
        "https://example.com/jpx?date={date}",
        target_date=date(2026, 3, 16),
        timeout=20,
        session=DummySession(fake_get),
    )
    records = fetcher.fetch()

    assert len(records) == 1
    assert records[0].company_code == "7203"
    assert records[0].company_name == "トヨタ自動車"
    assert records[0].title == "決算短信"
    assert records[0].source_url == "https://example.com/detail/7203-001.pdf?b=2&a=1#fragment"
    assert records[0].source_disclosure_id == "https://example.com/detail/7203-001.pdf?a=1&b=2"
    assert fetcher.last_diagnostics[0].status == "ok"



def test_jpx_tdnet_fetcher_reads_date_range(monkeypatch) -> None:
    urls: list[str] = []

    def fake_get(url: str, timeout: int):
        urls.append(url)
        if url.endswith("2026-03-15"):
            html = """
            <html><body><table>
              <tr><td>09:00</td><td>6758</td><td>ソニーグループ</td><td><a href="/detail/6758-001.pdf">適時開示</a></td></tr>
            </table></body></html>
            """
        else:
            html = """
            <html><body><table>
              <tr><td>09:30</td><td>6758</td><td>ソニーグループ</td><td><a href="/detail/6758-002.pdf">適時開示</a></td></tr>
            </table></body></html>
            """
        return DummyResponse(text=html)

    fetcher = JpxTdnetDisclosureFetcher(
        "https://example.com/jpx?date={date}",
        date_from=date(2026, 3, 15),
        date_to=date(2026, 3, 16),
        session=DummySession(fake_get),
    )
    records = fetcher.fetch()

    assert len(urls) == 2
    assert "https://example.com/jpx?date=2026-03-15" in urls
    assert "https://example.com/jpx?date=2026-03-16" in urls
    assert len(records) == 2



def test_jpx_tdnet_fetcher_distinguishes_normal_zero(monkeypatch) -> None:
    html = "<html><body><table><tr><th>時刻</th><th>コード</th><th>会社名</th><th>表題</th></tr></table></body></html>"

    def fake_get(url: str, timeout: int):
        return DummyResponse(text=html)

    fetcher = JpxTdnetDisclosureFetcher(
        "https://example.com/jpx?date={date}",
        target_date=date(2026, 3, 16),
        session=DummySession(fake_get),
    )

    records = fetcher.fetch()

    assert records == []
    assert fetcher.last_diagnostics[0].status == "normal_zero"
    assert fetcher.last_diagnostics[0].reason == "no_data_rows_found"



def test_jpx_tdnet_fetcher_raises_for_structure_anomaly_zero(monkeypatch) -> None:
    html = "<html><body><div>No table here</div></body></html>"

    def fake_get(url: str, timeout: int):
        return DummyResponse(text=html)

    fetcher = JpxTdnetDisclosureFetcher(
        "https://example.com/jpx?date={date}",
        target_date=date(2026, 3, 16),
        session=DummySession(fake_get),
    )

    with pytest.raises(ValueError, match="structure anomaly"):
        fetcher.fetch()



def test_jpx_tdnet_fetcher_sets_retry_and_user_agent() -> None:
    session = requests.Session()
    fetcher = JpxTdnetDisclosureFetcher(
        "https://example.com/jpx?date={date}",
        session=session,
        retry_count=3,
        user_agent=DEFAULT_USER_AGENT,
    )

    assert fetcher.session.headers["User-Agent"] == DEFAULT_USER_AGENT



def test_same_day_reingestion_does_not_increase_duplicates() -> None:
    session = _build_session()
    repository = DisclosureRepository(session)
    payload = DisclosureCreateInput(
        company_code="7203",
        company_name="トヨタ自動車",
        source_name="jpx-tdnet",
        disclosed_at=datetime.fromisoformat("2026-03-16T15:00:00+09:00"),
        title="決算短信",
        source_url="https://example.com/detail/7203-001.pdf",
        source_disclosure_id="https://example.com/detail/7203-001.pdf",
    )

    first = repository.bulk_upsert([payload])
    second = repository.bulk_upsert([payload])

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["skipped"] == 1
