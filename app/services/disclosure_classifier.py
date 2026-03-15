from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.models.enums import DisclosureCategory, DisclosurePriority
from app.services.disclosure_normalizer import normalize_disclosure_title


@dataclass(frozen=True)
class ClassificationResult:
    normalized_title: str
    category: DisclosureCategory
    priority: DisclosurePriority
    is_analysis_target: bool
    classification_reason: str


@dataclass(frozen=True)
class RuleDefinition:
    category: DisclosureCategory
    priority: DisclosurePriority
    is_analysis_target: bool
    keywords_any: tuple[str, ...]


class DisclosureClassifier:
    def __init__(self, rules_path: str | Path | None = None) -> None:
        self.rules_path = Path(rules_path) if rules_path else _default_rules_path()
        self.rules = load_rule_definitions(self.rules_path)

    def classify(self, title: str) -> ClassificationResult:
        normalized_title = normalize_disclosure_title(title)
        matched_rules = [
            rule
            for rule in self.rules
            if any(keyword in normalized_title for keyword in rule.keywords_any)
        ]

        if not matched_rules:
            return ClassificationResult(
                normalized_title=normalized_title,
                category=DisclosureCategory.UNKNOWN,
                priority=DisclosurePriority.LOW,
                is_analysis_target=False,
                classification_reason="No classification keywords matched.",
            )

        selected_rule = self._select_rule(matched_rules)
        matched_keywords = sorted(
            {
                keyword
                for rule in matched_rules
                for keyword in rule.keywords_any
                if keyword in normalized_title
            }
        )

        reason = (
            f"Matched category={selected_rule.category.value}; "
            f"keywords={', '.join(matched_keywords)}"
        )
        if len({rule.category for rule in matched_rules}) > 1:
            reason += "; multiple categories matched, selected highest-priority rule."

        return ClassificationResult(
            normalized_title=normalized_title,
            category=selected_rule.category,
            priority=selected_rule.priority,
            is_analysis_target=selected_rule.is_analysis_target,
            classification_reason=reason,
        )

    @staticmethod
    def _select_rule(matched_rules: list[RuleDefinition]) -> RuleDefinition:
        category_rank = {
            DisclosureCategory.EARNINGS_REPORT: 5,
            DisclosureCategory.GUIDANCE_REVISION: 4,
            DisclosureCategory.DIVIDEND_REVISION: 3,
            DisclosureCategory.SHARE_BUYBACK: 2,
            DisclosureCategory.OTHER: 1,
            DisclosureCategory.UNKNOWN: 0,
        }
        return sorted(
            matched_rules,
            key=lambda rule: (
                category_rank[rule.category],
                len(rule.keywords_any),
            ),
            reverse=True,
        )[0]


@lru_cache(maxsize=1)
def load_rule_definitions(rules_path: Path) -> tuple[RuleDefinition, ...]:
    raw = json.loads(rules_path.read_text(encoding="utf-8"))
    definitions: list[RuleDefinition] = []
    for category_name, body in raw["categories"].items():
        definitions.append(
            RuleDefinition(
                category=DisclosureCategory(category_name),
                priority=DisclosurePriority(body["priority"]),
                is_analysis_target=bool(body["is_analysis_target"]),
                keywords_any=tuple(normalize_disclosure_title(keyword) for keyword in body["keywords_any"]),
            )
        )
    return tuple(definitions)


def _default_rules_path() -> Path:
    return Path(__file__).resolve().parent.parent / "rules" / "disclosure_classification_rules.json"
