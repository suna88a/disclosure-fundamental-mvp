import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import get_settings


@dataclass(frozen=True)
class PipelineStep:
    name: str
    command: list[str]
    required: bool
    description: str


def _default_disclosure_source(settings) -> str:
    if settings.jpx_disclosure_url_template:
        return "jpx-tdnet"
    if settings.disclosure_source_url:
        return "http-json"
    return "dummy"



def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the disclosure-driven MVP pipeline sequentially.")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to invoke each job script.",
    )
    parser.add_argument(
        "--disclosure-source",
        default=_default_disclosure_source(settings),
        choices=["dummy", "http-json", "jpx-tdnet"],
        help="Disclosure fetch source backend.",
    )
    parser.add_argument(
        "--disclosure-input",
        default="data/samples/disclosures_sample.json",
        help="Input file for the dummy disclosure fetcher.",
    )
    parser.add_argument(
        "--disclosure-url",
        default=settings.disclosure_source_url or "",
        help="HTTP JSON disclosure feed URL for the http-json disclosure fetcher.",
    )
    parser.add_argument(
        "--disclosure-url-template",
        default=settings.jpx_disclosure_url_template or "",
        help="JPX TDnet list URL template. Supports {date} (YYYY-MM-DD), {date_yyyymmdd} (YYYYMMDD), and optional {page}.",
    )
    parser.add_argument(
        "--disclosure-timeout",
        type=int,
        default=30,
        help="HTTP timeout seconds for the real disclosure fetcher.",
    )
    parser.add_argument(
        "--disclosure-date",
        default="",
        help="Target date in YYYY-MM-DD format for real disclosure fetchers.",
    )
    parser.add_argument(
        "--disclosure-date-from",
        default="",
        help="Range start date in YYYY-MM-DD format for real disclosure fetchers.",
    )
    parser.add_argument(
        "--disclosure-date-to",
        default="",
        help="Range end date in YYYY-MM-DD format for real disclosure fetchers.",
    )
    parser.add_argument(
        "--pdf-source",
        default="dummy",
        choices=["dummy"],
        help="PDF URL resolver backend.",
    )
    parser.add_argument(
        "--pdf-manifest",
        default="data/samples/pdf_links_sample.json",
        help="Manifest file for the dummy PDF resolver.",
    )
    parser.add_argument(
        "--pdf-storage-dir",
        default="data/pdf",
        help="Local directory for downloaded PDFs.",
    )
    parser.add_argument(
        "--revision-source",
        default="dummy",
        choices=["dummy"],
        help="Revision extraction backend.",
    )
    parser.add_argument(
        "--revision-manifest",
        default="data/samples/revision_extractions_sample.json",
        help="Manifest file for the dummy revision extractor.",
    )
    parser.add_argument(
        "--financial-source",
        default="dummy",
        choices=["dummy"],
        help="Financial report parser backend.",
    )
    parser.add_argument(
        "--financial-manifest",
        default="data/samples/financial_reports_sample.json",
        help="Manifest file for the dummy financial report parser.",
    )
    parser.add_argument(
        "--skip-reclassify",
        action="store_true",
        help="Skip the reclassification step. Keep enabled when fetch already classifies titles.",
    )
    return parser.parse_args()



def build_steps(args: argparse.Namespace) -> list[PipelineStep]:
    python_executable = args.python
    fetch_command = [
        python_executable,
        "-m",
        "scripts.run_disclosure_fetch",
        "--source",
        args.disclosure_source,
        "--input",
        args.disclosure_input,
        "--url",
        args.disclosure_url,
        "--url-template",
        args.disclosure_url_template,
        "--timeout",
        str(args.disclosure_timeout),
    ]
    if args.disclosure_date:
        fetch_command.extend(["--date", args.disclosure_date])
    if args.disclosure_date_from:
        fetch_command.extend(["--date-from", args.disclosure_date_from])
    if args.disclosure_date_to:
        fetch_command.extend(["--date-to", args.disclosure_date_to])

    return [
        PipelineStep(
            name="fetch_disclosures",
            command=fetch_command,
            required=True,
            description="Fetch new disclosures and persist them with dedupe.",
        ),
        PipelineStep(
            name="reclassify_disclosures",
            command=[
                python_executable,
                "-m",
                "scripts.reclassify_disclosures",
            ],
            required=False,
            description="Re-apply title normalization and classification rules to existing disclosures.",
        ),
        PipelineStep(
            name="download_pdfs",
            command=[
                python_executable,
                "-m",
                "scripts.run_pdf_download",
                "--source",
                args.pdf_source,
                "--manifest",
                args.pdf_manifest,
                "--storage-dir",
                args.pdf_storage_dir,
            ],
            required=False,
            description="Resolve PDF URLs for analysis targets and download missing files.",
        ),
        PipelineStep(
            name="extract_revisions",
            command=[
                python_executable,
                "-m",
                "scripts.run_revision_extraction",
                "--source",
                args.revision_source,
                "--manifest",
                args.revision_manifest,
            ],
            required=False,
            description="Extract standalone guidance/dividend revisions and generate minimal analysis results.",
        ),
        PipelineStep(
            name="extract_financial_reports",
            command=[
                python_executable,
                "-m",
                "scripts.run_financial_report_extraction",
                "--source",
                args.financial_source,
                "--manifest",
                args.financial_manifest,
            ],
            required=False,
            description="Extract earnings-report metrics and company forecasts from supported PDFs.",
        ),
        PipelineStep(
            name="run_financial_comparisons",
            command=[python_executable, "-m", "scripts.run_financial_comparisons"],
            required=False,
            description="Compute progress rate and comparison-based interpretation inputs.",
        ),
        PipelineStep(
            name="build_valuation_views",
            command=[python_executable, "-m", "scripts.run_valuation_views"],
            required=False,
            description="Build conservative valuation-change hypotheses from analysis results.",
        ),
        PipelineStep(
            name="dispatch_notifications",
            command=[python_executable, "-m", "scripts.run_notifications"],
            required=False,
            description="Send non-duplicate notifications for should_notify disclosures.",
        ),
        PipelineStep(
            name="dispatch_raw_notifications",
            command=[python_executable, "-m", "scripts.run_raw_notifications"],
            required=False,
            description="Send batched raw-market disclosure notifications to the secondary channel.",
        ),
    ]



def run_step(step: PipelineStep, workdir: Path) -> int:
    completed = subprocess.run(step.command, cwd=workdir, check=False)
    return completed.returncode



def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")



def main() -> None:
    args = parse_args()
    workdir = Path(__file__).resolve().parents[1]
    failures: list[tuple[str, int]] = []

    steps = build_steps(args)
    for step in steps:
        if step.name == "reclassify_disclosures" and args.skip_reclassify:
            log(f"[skip] {step.name}: skipped by option")
            continue

        log(f"[run] {step.name}: {step.description}")
        exit_code = run_step(step, workdir)
        if exit_code == 0:
            log(f"[ok]  {step.name}")
            continue

        failures.append((step.name, exit_code))
        if step.required:
            log(f"[stop] {step.name} failed with exit code {exit_code}")
            break
        log(f"[warn] {step.name} failed with exit code {exit_code}; continuing")

    if failures:
        summary = ", ".join(f"{name}={code}" for name, code in failures)
        log(f"Pipeline finished with failures: {summary}")
        raise SystemExit(1)

    log("Pipeline finished successfully.")


if __name__ == "__main__":
    main()
