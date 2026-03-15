from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    path: str
    expected_status: int
    body_contains: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run minimal HTTP smoke tests against the deployed app.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1",
        help="Base URL for smoke tests. Example: http://127.0.0.1 or https://example.com",
    )
    return parser.parse_args()


def build_checks() -> list[SmokeCheck]:
    return [
        SmokeCheck(name="health", path="/health", expected_status=200, body_contains='"status":"ok"'),
        SmokeCheck(name="disclosures", path="/disclosures", expected_status=200, body_contains="新着開示"),
        SmokeCheck(name="jobs", path="/jobs", expected_status=200, body_contains="ジョブ状況"),
        SmokeCheck(name="notifications", path="/notifications", expected_status=200, body_contains="通知履歴"),
        SmokeCheck(name="static", path="/static/styles.css", expected_status=200, body_contains=":root"),
    ]


def run_check(base_url: str, check: SmokeCheck) -> tuple[bool, str]:
    url = f"{base_url.rstrip('/')}{check.path}"
    try:
        with urlopen(url, timeout=10) as response:
            status = response.getcode()
            body = response.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        return False, f"{check.name}: expected {check.expected_status}, got HTTP {exc.code} ({url})"
    except URLError as exc:
        return False, f"{check.name}: connection failed ({url}) - {exc.reason}"

    if status != check.expected_status:
        return False, f"{check.name}: expected {check.expected_status}, got {status} ({url})"

    if check.body_contains and check.body_contains not in body:
        return False, f"{check.name}: response missing expected text '{check.body_contains}' ({url})"

    return True, f"{check.name}: ok ({status})"


def main() -> None:
    args = parse_args()
    failures: list[str] = []
    for check in build_checks():
        ok, message = run_check(args.base_url, check)
        print(message)
        if not ok:
            failures.append(message)

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
