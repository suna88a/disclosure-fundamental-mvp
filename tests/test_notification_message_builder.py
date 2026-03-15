from datetime import datetime
from decimal import Decimal

from app.models.analysis_result import AnalysisResult
from app.models.company import Company
from app.models.disclosure import Disclosure
from app.models.enums import DisclosureCategory, DisclosurePriority
from app.models.valuation_view import ValuationView
from app.services.notification_message_builder import build_dedupe_key, build_notification_body


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
