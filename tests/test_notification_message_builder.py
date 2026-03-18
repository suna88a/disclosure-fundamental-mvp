from datetime import datetime
from decimal import Decimal

from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory, DisclosurePriority
from app.models.valuation_view import ValuationView
import app.services.notification_message_builder as notification_message_builder
from app.services.notification_message_builder import (
    RAW_CATEGORY_COLORS,
    DISCORD_EMBED_TOTAL_TEXT_LIMIT,
    build_dedupe_key,
    build_notification_body,
    build_raw_discord_batches,
    build_raw_disclosure_batches,
    build_raw_short_title,
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


def test_filter_raw_disclosures_excludes_etf_reit_infra_and_commodity_trusts() -> None:
    equity = Company(id=1, code="1111", name="個別株")
    reit = Company(id=2, code="2222", name="日本リート投資法人")
    etf = Company(id=3, code="3333", name="ＴＯＰＩＸ　ＥＴＦ")
    commodity_trust = Company(id=4, code="1541", name="純プラチナ上場信託(現物国内保管型)")
    spdr = Company(id=5, code="1326", name="SPDRゴールド・シェア")

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
            title="ｅｔｆに関するお知らせ",
            category=DisclosureCategory.OTHER,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/etf",
            is_new=True,
            is_analysis_target=False,
        ),
        Disclosure(
            id=4,
            company_id=4,
            company=commodity_trust,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat("2026-03-13T15:03:00+09:00"),
            title="分配金のお知らせ",
            category=DisclosureCategory.OTHER,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/commodity",
            is_new=True,
            is_analysis_target=False,
        ),
        Disclosure(
            id=5,
            company_id=5,
            company=spdr,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat("2026-03-13T15:04:00+09:00"),
            title="SPDRゴールド・シェアに関するお知らせ",
            category=DisclosureCategory.OTHER,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/spdr",
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


def test_build_raw_short_title_applies_rule_based_shortening() -> None:
    assert build_raw_short_title("業績予想の修正に関するお知らせ") == "業績予想修正"
    assert build_raw_short_title("特別損失の計上に関するお知らせ") == "特損計上"


def test_build_raw_discord_batches_creates_summary_and_category_embeds() -> None:
    company = Company(id=1, code="7203", name="Toyota", name_ja="トヨタ自動車")
    disclosures = [
        Disclosure(
            id=1,
            company_id=1,
            company=company,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat("2026-03-13T15:00:00+09:00"),
            title="決算短信に関するお知らせ",
            category=DisclosureCategory.EARNINGS_REPORT,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/1",
            is_new=False,
            is_analysis_target=False,
        ),
        Disclosure(
            id=2,
            company_id=1,
            company=company,
            source_name="jpx-tdnet",
            disclosed_at=datetime.fromisoformat("2026-03-13T15:10:00+09:00"),
            title="業績予想の修正に関するお知らせ",
            category=DisclosureCategory.OTHER,
            priority=DisclosurePriority.LOW,
            source_url="https://example.com/2",
            is_new=False,
            is_analysis_target=False,
        ),
    ]

    batches = build_raw_discord_batches(disclosures=disclosures, filtered_out_count=3, batch_size=10)

    assert len(batches) == 1
    embeds = batches[0].payload["embeds"]
    assert embeds[0]["title"] == "全市場 新規開示 2件"
    assert "除外 3" in embeds[0]["description"]
    assert any(embed["title"] == "決算短信 1件" for embed in embeds[1:])
    assert any(embed["title"] == "業績修正 1件" for embed in embeds[1:])
    earnings_embed = next(embed for embed in embeds if embed["title"] == "決算短信 1件")
    assert earnings_embed["color"] == RAW_CATEGORY_COLORS["earnings"]
    assert "15:00" in earnings_embed["description"]
    assert "7203" in earnings_embed["description"]
    assert "トヨタ自動車" in earnings_embed["description"]
    assert "要約:" not in earnings_embed["description"]
    assert "PDF: <https://example.com/1>" in earnings_embed["description"]


def test_build_raw_discord_batches_splits_other_category_without_ellipsis() -> None:
    company = Company(id=1, code="9999", name="Other Co")
    disclosures = []
    for idx in range(1, 8):
        disclosures.append(
            Disclosure(
                id=idx,
                company_id=1,
                company=company,
                source_name="jpx-tdnet",
                disclosed_at=datetime.fromisoformat(f"2026-03-13T10:0{idx}:00+09:00"),
                title=f"その他開示{idx}に関するお知らせ",
                category=DisclosureCategory.OTHER,
                priority=DisclosurePriority.LOW,
                source_url=f"https://example.com/other/{idx}",
                is_new=False,
                is_analysis_target=False,
            )
        )

    batches = build_raw_discord_batches(disclosures=disclosures, filtered_out_count=0, batch_size=3)
    other_embeds = [embed for batch in batches for embed in batch.payload["embeds"] if embed["title"].startswith("その他 7件")]

    assert len(other_embeds) == 3
    assert other_embeds[0]["title"] == "その他 7件(1/3)"
    assert other_embeds[1]["title"] == "その他 7件(2/3)"
    assert other_embeds[2]["title"] == "その他 7件(3/3)"
    assert all("他 " not in embed["description"] for embed in other_embeds)
    combined = "\n".join(embed["description"] for embed in other_embeds)
    assert "https://example.com/other/7" in combined


def test_build_raw_discord_batches_splits_when_total_embed_text_would_exceed_limit(monkeypatch) -> None:
    company = Company(id=1, code="7203", name="Toyota", name_ja="トヨタ自動車")
    long_title = "業績予想の修正に関するお知らせ" + "A" * 400
    disclosures = []
    for idx in range(1, 19):
        disclosures.append(
            Disclosure(
                id=idx,
                company_id=1,
                company=company,
                source_name="jpx-tdnet",
                disclosed_at=datetime.fromisoformat(f"2026-03-13T15:{idx % 60:02d}:00+09:00"),
                title=long_title,
                category=DisclosureCategory.OTHER,
                priority=DisclosurePriority.LOW,
                source_url=f"https://example.com/limit/{idx}",
                is_new=False,
                is_analysis_target=False,
            )
        )

    monkeypatch.setattr(notification_message_builder, "DISCORD_EMBED_TOTAL_TEXT_LIMIT", 900)
    batches = build_raw_discord_batches(disclosures=disclosures, filtered_out_count=0, batch_size=3)

    assert len(batches) >= 2
    for batch in batches:
        embeds = batch.payload["embeds"]
        total_chars = sum(len(str(embed.get("title") or "")) + len(str(embed.get("description") or "")) for embed in embeds)
        assert total_chars <= DISCORD_EMBED_TOTAL_TEXT_LIMIT
