from datetime import datetime
from decimal import Decimal

from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory, DisclosurePriority
from app.models.valuation_view import ValuationView
from app.services.notification_message_builder import (
    build_dedupe_key,
    build_notification_body,
    build_raw_disclosure_batches,
    classify_raw_disclosure,
    filter_raw_disclosures,
)


def test_build_notification_body_contains_required_fields() -> None:
    company = Company(id=1, code="6758", name="Sony Group", name_ja="ソニーグループ")
    disclosure = Disclosure(
        id=10,
        company_id=1,
        company=company,
        source_name="dummy",
        disclosed_at=datetime.fromisoformat("2026-03-13T15:00:00+09:00"),
        title="Summary of Consolidated Financial Results",
        category=DisclosureCategory.EARNINGS_REPORT,
        priority=DisclosurePriority.CRITICAL,
        source_url="https://example.com/disclosure",
        is_new=True,
        is_analysis_target=True,
    )
    analysis = AnalysisResult(disclosure_id=10, auto_summary="進捗率80% / 業績予想上方修正", overall_score=Decimal("3.0"))
    valuation = ValuationView(
        disclosure_id=10,
        eps_revision_view="EPSの上振れ余地が意識されやすい。",
        short_term_reaction_view="短期反応はポジティブ寄りを想定。",
        valuation_comment="仮説コメント",
    )

    body = build_notification_body(
        disclosure=disclosure,
        analysis=analysis,
        valuation=valuation,
        web_base_url="https://example.com/app",
    )

    assert "6758" in body
    assert "ソニーグループ" in body
    assert "開示種別: 決算短信" in body
    assert "要点:" in body
    assert "auto_summary" not in body
    assert "見立て:" in body
    assert "https://example.com/app/disclosures/10" in body


def test_build_dedupe_key_is_stable() -> None:
    key = build_dedupe_key(
        disclosure_id=10,
        notification_type="analysis_alert",
        channel="dummy",
        destination="test-room",
    )
    assert key == "10:analysis_alert:dummy:test-room"



def test_build_raw_disclosure_batches_splits_by_batch_size() -> None:
    company = Company(id=1, code="6758", name="Sony Group", name_ja="ソニーグループ")
    disclosures = []
    for idx, title in enumerate(["決算短信", "業績予想の修正に関するお知らせ", "配当予想の修正に関するお知らせ"], start=1):
        disclosures.append(
            Disclosure(
                id=idx,
                company_id=1,
                company=company,
                source_name="jpx-tdnet",
                disclosed_at=datetime.fromisoformat(f"2026-03-13T15:0{idx-1}:00+09:00"),
                title=title,
                category=DisclosureCategory.OTHER,
                priority=DisclosurePriority.LOW,
                source_url=f"https://example.com/disclosure/{idx}",
                is_new=True,
                is_analysis_target=False,
            )
        )

    batches = build_raw_disclosure_batches(disclosures=disclosures, batch_size=2, max_chars=1000)

    assert len(batches) == 2
    assert len(batches[0][0]) == 2
    assert len(batches[1][0]) == 1
    assert "全市場 新規開示" in batches[0][1]
    assert "件】" in batches[0][1]
    assert "【決算短信 1件】" in batches[0][1] or "【業績修正 1件】" in batches[0][1]


def test_filter_raw_disclosures_excludes_etf_reit_and_infra() -> None:
    equity = Company(id=1, code="1111", name="個別株")
    reit = Company(id=2, code="2222", name="日本リート投資法人")
    etf = Company(id=3, code="3333", name="TOPIX ETF")

    disclosures = [
        Disclosure(
            id=1,
            company_id=1,
            company=equity,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat("2026-03-13T15:00:00+09:00"),
            title="決算短信",
            category=DisclosureCategory.EARNINGS_REPORT,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/equity",
            is_new=True,
            is_analysis_target=False,
        ),
        Disclosure(
            id=2,
            company_id=2,
            company=reit,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat("2026-03-13T15:01:00+09:00"),
            title="運用状況のお知らせ",
            category=DisclosureCategory.OTHER,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/reit",
            is_new=True,
            is_analysis_target=False,
        ),
        Disclosure(
            id=3,
            company_id=3,
            company=etf,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat("2026-03-13T15:02:00+09:00"),
            title="ETFに関するお知らせ",
            category=DisclosureCategory.OTHER,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/etf",
            is_new=True,
            is_analysis_target=False,
        ),
    ]

    filtered = filter_raw_disclosures(disclosures)

    assert [disclosure.id for disclosure in filtered] == [1]



def test_classify_raw_disclosure_prioritizes_guidance_over_dividend() -> None:
    company = Company(id=1, code="1111", name="個別株")
    disclosure = Disclosure(
        id=1,
        company_id=1,
        company=company,
        source_name="jpx-tdnet",
        disclosed_at=datetime.fromisoformat("2026-03-13T15:00:00+09:00"),
        title="業績予想及び配当予想の修正に関するお知らせ",
        category=DisclosureCategory.OTHER,
        priority=DisclosurePriority.LOW,
        source_url="https://example.com/mixed",
        is_new=True,
        is_analysis_target=False,
    )

    assert classify_raw_disclosure(disclosure) == "guidance"
