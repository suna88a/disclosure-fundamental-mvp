from app.models.enums import DisclosureCategory, DisclosurePriority
from app.services.disclosure_classifier import DisclosureClassifier
from app.services.disclosure_normalizer import normalize_disclosure_title


def test_normalize_disclosure_title_collapses_case_and_spacing() -> None:
    title = "  Summary   of   Consolidated Financial Results  "
    assert normalize_disclosure_title(title) == "summary of consolidated financial results"


def test_classify_earnings_report() -> None:
    classifier = DisclosureClassifier()
    result = classifier.classify("2026年3月期 第3四半期決算短信〔日本基準〕(連結)")
    assert result.category == DisclosureCategory.EARNINGS_REPORT
    assert result.priority == DisclosurePriority.CRITICAL
    assert result.is_analysis_target is True


def test_classify_guidance_revision() -> None:
    classifier = DisclosureClassifier()
    result = classifier.classify("業績予想の修正に関するお知らせ")
    assert result.category == DisclosureCategory.GUIDANCE_REVISION
    assert result.priority == DisclosurePriority.HIGH
    assert result.is_analysis_target is True


def test_classify_dividend_revision() -> None:
    classifier = DisclosureClassifier()
    result = classifier.classify("配当予想の修正に関するお知らせ")
    assert result.category == DisclosureCategory.DIVIDEND_REVISION
    assert result.is_analysis_target is True


def test_classify_share_buyback() -> None:
    classifier = DisclosureClassifier()
    result = classifier.classify("自己株式の取得に係る事項の決定に関するお知らせ")
    assert result.category == DisclosureCategory.SHARE_BUYBACK
    assert result.is_analysis_target is True


def test_unknown_when_no_keywords_match() -> None:
    classifier = DisclosureClassifier()
    result = classifier.classify("役員人事に関するお知らせ")
    assert result.category == DisclosureCategory.UNKNOWN
    assert result.priority == DisclosurePriority.LOW
    assert result.is_analysis_target is False
