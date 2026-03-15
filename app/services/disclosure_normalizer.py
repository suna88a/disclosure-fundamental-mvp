import re
import unicodedata


_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[!-/:-@[-`{-~]")


def normalize_disclosure_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).strip().lower()
    normalized = normalized.replace("（訂正）", "訂正")
    normalized = normalized.replace("(correction)", "correction")
    normalized = normalized.replace("㈱", "株式会社")
    normalized = _PUNCTUATION_RE.sub(" ", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()
