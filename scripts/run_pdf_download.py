import argparse

from app.fetchers.pdf_url_resolver import DummyPdfUrlResolver
from app.jobs.runner import run_job
from app.services.pdf_downloader import PdfDownloader
from app.services.pdf_ingestion import ingest_pdfs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve and download disclosure PDFs.")
    parser.add_argument(
        "--source",
        default="dummy",
        choices=["dummy"],
        help="PDF URL source backend.",
    )
    parser.add_argument(
        "--manifest",
        default="data/samples/pdf_links_sample.json",
        help="Manifest path for the dummy PDF resolver.",
    )
    parser.add_argument(
        "--storage-dir",
        default="data/pdf",
        help="Local storage directory for downloaded PDFs.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all target disclosures instead of only pending ones.",
    )
    return parser.parse_args()


def build_resolver(args: argparse.Namespace) -> DummyPdfUrlResolver:
    if args.source == "dummy":
        return DummyPdfUrlResolver(args.manifest)
    raise ValueError(f"Unsupported source: {args.source}")


def main() -> None:
    args = parse_args()
    resolver = build_resolver(args)
    downloader = PdfDownloader(args.storage_dir)

    def job(context):
        result = ingest_pdfs(
            context.session,
            resolver=resolver,
            downloader=downloader,
            only_pending=not args.all,
        )
        context.set_processed_count(result["processed"])
        return result

    result = run_job("download_pdfs", job)
    print(result)


if __name__ == "__main__":
    main()
