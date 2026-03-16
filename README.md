# Disclosure Fundamental MVP

Japanese equity disclosure monitoring and fundamental analysis MVP.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# If the schema changed, delete the old DB first:
# Remove-Item data/app.db -Force
python -m scripts.init_db
python -m scripts.load_companies --input data/samples/companies_sample.csv
python -m scripts.run_disclosure_fetch --source dummy --input data/samples/disclosures_sample.json
python -m scripts.reclassify_disclosures --only-unclassified
python -m scripts.run_pdf_download --source dummy --manifest data/samples/pdf_links_sample.json
python -m scripts.run_revision_extraction --source dummy --manifest data/samples/revision_extractions_sample.json
python -m scripts.run_financial_report_extraction --source dummy --manifest data/samples/financial_reports_sample.json
python -m scripts.run_financial_comparisons
python -m scripts.run_valuation_views
python -m scripts.run_notifications
uvicorn app.main:app --reload
```

## Companies CSV Format

Recommended file split:

- `data/master/companies_master.csv` : operational source of truth
- `data/samples/companies_sample.csv` : local example and test data
- [companies_master.csv.example](c:\dev\suna88\data\master\companies_master.csv.example) : starter template for the operational master file

Recommended columns for `load_companies`:

- `code` : required
- `name` : required
- `name_ja` : optional but recommended
- `market` : optional
- `industry` : optional
- `is_active` : optional, defaults to `true`

Example:

```csv
code,name,name_ja,market,industry,is_active
7203,Toyota Motor Corporation,トヨタ自動車,Prime,Automobiles,true
6758,Sony Group Corporation,ソニーグループ,Prime,Electric Appliances,true
9432,Nippon Telegraph and Telephone Corporation,日本電信電話,Prime,Information and Communication,true
```

Operational rule for `name` and `name_ja`:

- `name` remains the required fallback company name.
- `name_ja` is preferred in UI and notification output when present.
- If `name_ja` is empty, the system falls back to `name`.
- For stable operation, keep `name` populated even when `name_ja` exists.

Load or reload companies:

```powershell
python -m scripts.load_companies --input data/master/companies_master.csv
```

If you changed the `companies` schema and your SQLite DB predates `name_ja`, recreate the DB before loading:

```powershell
Remove-Item data/app.db -Force
python -m scripts.init_db
python -m scripts.load_companies --input data/master/companies_master.csv
```

## Companies Master Maintenance

Recommended source policy:

- Keep one canonical CSV under `data/master/companies_master.csv`.
- Treat this file as the operational source of truth for `companies`.
- Use public market reference data or your own maintained spreadsheet as the upstream source, then export to this CSV format.
- Do not edit `data/samples/companies_sample.csv` for production use.

Recommended field ownership:

- `code`
  - unique primary business key
  - never repurpose an existing code for another company
- `name`
  - required fallback display name
  - keep it stable even if `name_ja` exists
- `name_ja`
  - preferred display label for UI and notifications
  - update when the Japanese legal or common display name changes
- `market`
  - keep aligned with the latest listing segment you want to display
- `industry`
  - keep aligned with your chosen reference classification
- `is_active`
  - use `true` for currently monitored/listed companies
  - use `false` instead of deleting rows when a code should remain in history but no longer be active

### Initial Load Flow

1. Create `data/master/companies_master.csv` from the example template.
2. Fill at minimum `code`, `name`, and preferably `name_ja`.
3. Initialize the DB.
4. Run:

```powershell
python -m scripts.load_companies --input data/master/companies_master.csv
```

5. Open `/disclosures` later and confirm Japanese names appear when `name_ja` is populated.

### Update Flow

For normal master maintenance:

1. Edit `data/master/companies_master.csv`.
2. Keep `code` unchanged for existing companies.
3. Add new rows for new codes.
4. Mark `is_active=false` for delisted or suspended names instead of removing them immediately.
5. Rerun:

```powershell
python -m scripts.load_companies --input data/master/companies_master.csv
```

The loader updates existing rows by `code` and inserts new ones.

### Update Rules By Code

`code` is the only key used for company master updates.

- same `code` + changed `name` or `name_ja` -> update the existing row
- same `code` + changed `market` or `industry` -> update the existing row
- same `code` + changed `is_active` -> update the existing row
- new `code` -> insert a new row

Do not change a company's code in place. If the exchange-side code truly changes, treat it as a new row and decide separately how to handle historical continuity.

### Existing CSV Update Notes

- Keep UTF-8 with BOM or UTF-8 encoding for Japanese names.
- Avoid blank `name`; loader treats it as invalid.
- Blank `name_ja` is allowed and falls back to `name`.
- If a column is removed or renamed, `load_companies` may fail on required fields.
- Because migrations are not implemented, schema changes still require DB recreation.

### is_active Policy

Use `is_active` for operational filtering, not for history deletion.

- `true`
  - active listed company
  - eligible for monitoring and normal display
- `false`
  - no longer active for current monitoring
  - kept in DB so old disclosures and notifications still resolve correctly

## Active Company Monitoring Rule

The monitoring rule is simple:

- `companies.is_active = true`
  - included in normal disclosure monitoring and downstream processing
- `companies.is_active = false`
  - excluded from new monitoring and downstream processing
  - historical rows remain in the database and stay viewable

This preserves disclosure history without continuing to spend processing and notification capacity on inactive names.

### Where Filtering Happens

Filtering is applied in two layers:

1. Disclosure ingestion
   - new fetched disclosures for inactive companies are skipped before insert
2. Downstream processing
   - PDF download
   - revision extraction
   - earnings extraction
   - comparison generation
   - valuation generation
   - notification dispatch
   all run only for `is_active = true`

This gives two protections:

- inactive companies do not create new monitored disclosures
- even if older rows already exist, downstream jobs stop processing them after the company is marked inactive

### Inactive Company History Policy

When a company is marked inactive:

- existing `disclosures` remain
- existing `pdf_files` remain
- existing `financial_reports`, `analysis_results`, `valuation_views`, and `notifications` remain
- historical detail pages continue to work

The system does not delete historical data when `is_active` changes to `false`.

### Existing Data Consistency

If a company is changed from active to inactive after some disclosures were already saved:

- old rows are kept as-is
- future `run_pdf_download`, `run_revision_extraction`, `run_financial_report_extraction`, `run_financial_comparisons`, `run_valuation_views`, and `run_notifications` will ignore that company
- if you later set `is_active` back to `true`, normal monitoring resumes on the next run

Operationally, this means `is_active` is the switch for future processing, not a signal to purge existing history.

## Production Deployment

Assumed production layout on a small VPS:

- app root: `/srv/disclosure-fundamental-mvp`
- virtualenv: `/srv/disclosure-fundamental-mvp/.venv`
- env file: `/srv/disclosure-fundamental-mvp/.env`
- SQLite DB: `/srv/disclosure-fundamental-mvp/data/app.db`
- PDF cache: `/srv/disclosure-fundamental-mvp/data/pdf`
- backups: `/srv/disclosure-fundamental-mvp/data/backups`
- logs: `/srv/disclosure-fundamental-mvp/logs`

Included deployment helpers:

- systemd unit: [disclosure-fundamental-web.service](c:\dev\suna88\deploy\systemd\disclosure-fundamental-web.service)
- nginx config example: [disclosure-fundamental.conf](c:\dev\suna88\deploy\nginx\disclosure-fundamental.conf)
- logrotate config example: [disclosure-fundamental](c:\dev\suna88\deploy\logrotate\disclosure-fundamental)
- production start script: [start_web.sh](c:\dev\suna88\scripts\start_web.sh)

### Deployment Steps

1. Place the repository under `/srv/disclosure-fundamental-mvp`.
2. Create the virtual environment and install dependencies:

```bash
cd /srv/disclosure-fundamental-mvp
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
mkdir -p logs data/pdf data/backups
python -m scripts.init_db
```

3. Edit `.env` for production at minimum:

```env
APP_ENV=production
DEBUG=false
DATABASE_URL=sqlite:///./data/app.db
WEB_BASE_URL=https://example.com
NOTIFICATION_CHANNEL=telegram
NOTIFICATION_DESTINATION=your-telegram-chat
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

4. Copy the systemd unit:

```bash
sudo cp deploy/systemd/disclosure-fundamental-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable disclosure-fundamental-web.service
sudo systemctl start disclosure-fundamental-web.service
```

5. Copy the nginx config:

```bash
sudo cp deploy/nginx/disclosure-fundamental.conf /etc/nginx/sites-available/disclosure-fundamental.conf
sudo ln -s /etc/nginx/sites-available/disclosure-fundamental.conf /etc/nginx/sites-enabled/disclosure-fundamental.conf
sudo nginx -t
sudo systemctl reload nginx
```

### Service Control

Start:

```bash
sudo systemctl start disclosure-fundamental-web.service
```

Restart:

```bash
sudo systemctl restart disclosure-fundamental-web.service
```

Stop:

```bash
sudo systemctl stop disclosure-fundamental-web.service
```

Status:

```bash
sudo systemctl status disclosure-fundamental-web.service
```

Recent logs:

```bash
tail -n 100 /srv/disclosure-fundamental-mvp/logs/web.log
tail -n 100 /srv/disclosure-fundamental-mvp/logs/web-error.log
tail -n 100 /srv/disclosure-fundamental-mvp/logs/pipeline.log
```

## Post-Deploy Checklist

Run these checks in order right after deployment:

1. Confirm the web service is running:

```bash
sudo systemctl status disclosure-fundamental-web.service --no-pager
```

2. Confirm nginx config is valid and loaded:

```bash
sudo nginx -t
sudo systemctl status nginx --no-pager
```

3. Confirm the app responds locally:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/disclosures | head
curl -fsS http://127.0.0.1:8000/jobs | head
curl -fsS http://127.0.0.1:8000/notifications | head
```

4. Confirm nginx proxying and static delivery:

```bash
curl -fsS http://127.0.0.1/health
curl -I http://127.0.0.1/static/styles.css
```

5. Confirm the pipeline runs:

```bash
cd /srv/disclosure-fundamental-mvp
.venv/bin/python -m scripts.run_pipeline
```

6. Confirm backup and storage maintenance commands run:

```bash
.venv/bin/python -m scripts.backup_sqlite
.venv/bin/python -m scripts.manage_pdf_storage
```

## Smoke Test

Included smoke test script: [run_smoke_tests.py](c:\dev\suna88\scripts\run_smoke_tests.py)

Local app port check:

```bash
cd /srv/disclosure-fundamental-mvp
.venv/bin/python -m scripts.run_smoke_tests --base-url http://127.0.0.1:8000
```

nginx public route check:

```bash
cd /srv/disclosure-fundamental-mvp
.venv/bin/python -m scripts.run_smoke_tests --base-url http://127.0.0.1
```

This verifies:

- `/health`
- `/disclosures`
- `/jobs`
- `/notifications`
- `/static/styles.css`

## Runtime Verification Order

When checking production, use this order:

1. `systemd`
   - Is uvicorn running?
   - `sudo systemctl status disclosure-fundamental-web.service --no-pager`
2. `app`
   - Is FastAPI answering on `127.0.0.1:8000`?
   - `curl -fsS http://127.0.0.1:8000/health`
3. `nginx`
   - Is nginx proxying and serving `/static/`?
   - `curl -fsS http://127.0.0.1/health`
   - `curl -I http://127.0.0.1/static/styles.css`
4. `pipeline`
   - Does `run_pipeline` complete?
   - `.venv/bin/python -m scripts.run_pipeline`
5. `notifications`
   - For dummy mode, do notification rows appear in `/notifications` after pipeline execution?
   - If needed, temporarily set `NOTIFICATION_CHANNEL=dummy` and rerun `run_notifications`.

## Permission Checks

The service user must be able to write to:

- `/srv/disclosure-fundamental-mvp/logs`
- `/srv/disclosure-fundamental-mvp/data`
- `/srv/disclosure-fundamental-mvp/data/pdf`
- `/srv/disclosure-fundamental-mvp/data/backups`

Check with the systemd user:

```bash
sudo -u www-data test -w /srv/disclosure-fundamental-mvp/logs && echo logs-ok
sudo -u www-data test -w /srv/disclosure-fundamental-mvp/data && echo data-ok
sudo -u www-data test -w /srv/disclosure-fundamental-mvp/data/pdf && echo pdf-ok
sudo -u www-data test -w /srv/disclosure-fundamental-mvp/data/backups && echo backups-ok
```

If you also want an actual write test:

```bash
sudo -u www-data sh -c 'touch /srv/disclosure-fundamental-mvp/logs/.write-test && rm /srv/disclosure-fundamental-mvp/logs/.write-test'
sudo -u www-data sh -c 'touch /srv/disclosure-fundamental-mvp/data/.write-test && rm /srv/disclosure-fundamental-mvp/data/.write-test'
sudo -u www-data sh -c 'touch /srv/disclosure-fundamental-mvp/data/pdf/.write-test && rm /srv/disclosure-fundamental-mvp/data/pdf/.write-test'
sudo -u www-data sh -c 'touch /srv/disclosure-fundamental-mvp/data/backups/.write-test && rm /srv/disclosure-fundamental-mvp/data/backups/.write-test'
```

## Dummy Notification Check

To verify notification flow without Telegram:

```bash
cd /srv/disclosure-fundamental-mvp
NOTIFICATION_CHANNEL=dummy .venv/bin/python -m scripts.run_notifications
curl -fsS http://127.0.0.1:8000/notifications | head
```

## First Logs To Check On Failure

Check logs in this order:

1. `sudo systemctl status disclosure-fundamental-web.service --no-pager`
2. `tail -n 100 /srv/disclosure-fundamental-mvp/logs/web-error.log`
3. `tail -n 100 /srv/disclosure-fundamental-mvp/logs/pipeline.log`
4. `tail -n 100 /srv/disclosure-fundamental-mvp/logs/nginx-error.log`

Interpretation:

- web service not starting: check `systemd` status and `web-error.log`
- app route failing locally: check `web-error.log`
- pipeline failing: check `pipeline.log`
- nginx only failing: check `nginx-error.log`

## Static File Check

The nginx config is expected to serve `/static/` from `/srv/disclosure-fundamental-mvp/app/static/`.

Current app static directory:

- [styles.css](c:\dev\suna88\app\static\styles.css)

Quick check:

```bash
test -f /srv/disclosure-fundamental-mvp/app/static/styles.css && echo static-file-ok
curl -I http://127.0.0.1/static/styles.css
```

If `/static/styles.css` returns `404`, check the nginx `alias` path before investigating FastAPI.

### Cron for Pipeline

Keep the web app under `systemd` and run the pipeline separately with cron:

```cron
*/15 * * * * cd /srv/disclosure-fundamental-mvp && /srv/disclosure-fundamental-mvp/.venv/bin/python -m scripts.run_pipeline >> /srv/disclosure-fundamental-mvp/logs/pipeline.log 2>&1
```

This keeps the responsibilities separate:

- `systemd`: web process supervision
- `cron`: sequential disclosure pipeline execution
- `nginx`: reverse proxy and static file serving

### Logrotate

Included example: [disclosure-fundamental](c:\dev\suna88\deploy\logrotate\disclosure-fundamental)

Target logs:

- `/srv/disclosure-fundamental-mvp/logs/web.log`
- `/srv/disclosure-fundamental-mvp/logs/web-error.log`
- `/srv/disclosure-fundamental-mvp/logs/pipeline.log`
- `/srv/disclosure-fundamental-mvp/logs/nginx-access.log`
- `/srv/disclosure-fundamental-mvp/logs/nginx-error.log`

Policy:

- rotate daily
- keep 14 generations
- compress old logs
- keep the newest rotated file uncompressed until the next cycle (`delaycompress`)
- use `copytruncate` to avoid forcing a process restart just for log rotation

Apply:

```bash
sudo cp deploy/logrotate/disclosure-fundamental /etc/logrotate.d/disclosure-fundamental
sudo logrotate -d /etc/logrotate.d/disclosure-fundamental
sudo logrotate -f /etc/logrotate.d/disclosure-fundamental
```

Recommended rationale for a small VPS:

- `14` daily rotations gives roughly two weeks of local history.
- compression keeps old logs small.
- `copytruncate` is safer for this MVP because `web.log`, `web-error.log`, and `pipeline.log` are plain appended files, not journald-managed logs.

Operational notes:

- `systemd` status still remains the first check even if `web.log` is rotated.
- `nginx` logs in this setup are regular files under the app `logs/` directory, so they are included in the same rotation policy.
- if you later move nginx logs back to `/var/log/nginx`, split the nginx entries into a separate logrotate policy instead of reusing this one.
- if the service user changes from `www-data`, update the `su` line in the logrotate config.

### Logs Directory Policy

The MVP expects a writable `logs/` directory.

Recommended files:

- `logs/web.log`
- `logs/web-error.log`
- `logs/pipeline.log`
- `logs/nginx-access.log`
- `logs/nginx-error.log`

If the service does not start, check that `/srv/disclosure-fundamental-mvp/logs` exists and is writable by the service user.

## Daily Pipeline Order

Recommended daily execution order on a small VPS is strictly sequential:

1. `run_disclosure_fetch`
   - Role: fetch new disclosures and persist them with dedupe.
   - Dependency: none.
   - Failure handling: this is the only required first step. If it fails, stop the pipeline and let the next cron retry.
2. `reclassify_disclosures`
   - Role: re-apply normalization and classification rules to existing disclosures.
   - Dependency: disclosures must exist.
   - Failure handling: non-fatal. The next run can reclassify again.
3. `run_pdf_download`
   - Role: resolve PDF URLs and download only missing target files.
   - Dependency: classified disclosures.
   - Failure handling: non-fatal. Failed or missing URLs remain in state and can be retried later.
4. `run_revision_extraction`
   - Role: process standalone guidance/dividend revisions even without earnings PDFs.
   - Dependency: disclosures and, when available, downloaded PDFs.
   - Failure handling: non-fatal. Upsert behavior makes reruns safe.
5. `run_financial_report_extraction`
   - Role: extract supported earnings PDF metrics into `financial_reports`.
   - Dependency: downloaded PDFs.
   - Failure handling: non-fatal. Unsupported or failed parses keep explicit parse status for the next run.
6. `run_financial_comparisons`
   - Role: calculate `progress_rate_operating_income` and comparison-based interpretation inputs.
   - Dependency: `financial_reports`, plus revision tables when available.
   - Failure handling: non-fatal. Comparison status/reason preserves partial progress.
7. `run_valuation_views`
   - Role: generate conservative market re-rating hypotheses from `analysis_results`.
   - Dependency: analysis results must exist.
   - Failure handling: non-fatal. Can be rebuilt safely on the next run.
8. `run_notifications`
   - Role: send deduplicated notifications after all upstream interpretation steps are done.
   - Dependency: analysis and valuation views.
   - Failure handling: non-fatal. Deduped reruns prevent duplicate sends.

This order minimizes SQLite write contention by keeping jobs fully serial. Notifications remain last so they reflect the newest interpretation state.

## Daily Pipeline Script

You can run the whole sequence with one command:

```powershell
python -m scripts.run_pipeline
```

Example with explicit dummy inputs:

```powershell
python -m scripts.run_pipeline `
  --disclosure-source dummy `
  --disclosure-input data/samples/disclosures_sample.json `
  --pdf-source dummy `
  --pdf-manifest data/samples/pdf_links_sample.json `
  --revision-source dummy `
  --revision-manifest data/samples/revision_extractions_sample.json `
  --financial-source dummy `
  --financial-manifest data/samples/financial_reports_sample.json
```

Pipeline behavior:

- `fetch_disclosures` is treated as required. If it fails, the pipeline stops immediately.
- All later steps are best-effort. A failure is logged by each job in `job_runs`, the pipeline continues, and the next cron run can recover.
- Reruns are expected. Existing dedupe/upsert behavior is relied on instead of trying to make cron stateful.

## Cron Example

Linux cron example for every 15 minutes:

```cron
*/15 * * * * cd /srv/disclosure-mvp && /srv/disclosure-mvp/.venv/bin/python -m scripts.run_pipeline >> logs/pipeline.log 2>&1
```

Recommended cadence:

- Every 10 to 15 minutes during the day is enough for MVP operation.
- If you only need after-hours monitoring, run less frequently, for example every 30 minutes.
- Avoid overlapping cron entries. Keep one serial pipeline command instead of per-job cron rows.

## Re-run Safety

This MVP is designed around rerunnable jobs. The basic rule is: rerun the same job or the whole pipeline instead of editing DB rows manually.

Job-by-job rerun safety:

1. `run_disclosure_fetch`
   - Safe to rerun.
   - Duplicate prevention uses `source_disclosure_id` when available, otherwise `source_name + company_id + disclosed_at + title`.
   - If the fetch job fails partway, rerun it. Existing disclosures should be skipped.
2. `reclassify_disclosures`
   - Safe to rerun.
   - It recalculates normalized title, category, priority, and analysis-target flags for existing rows.
3. `run_pdf_download`
   - Safe to rerun.
   - Existing `pdf_files` rows are reused by `disclosure_id + source_url`.
   - Already downloaded files are not saved again, and missing-URL or failed states remain explicit.
4. `run_revision_extraction`
   - Safe to rerun.
   - `guidance_revisions`, `dividend_revisions`, and the minimal revision-based `analysis_results` path are upsert-based.
5. `run_financial_report_extraction`
   - Safe to rerun.
   - `financial_reports` is upsert-based and parse status is preserved on each `pdf_file`.
6. `run_financial_comparisons`
   - Safe to rerun.
   - It recalculates progress and comparison-backed interpretation state from current source tables.
7. `run_valuation_views`
   - Safe to rerun.
   - `valuation_views` is upsert-based and rebuilt from `analysis_results`.
8. `run_notifications`
   - Safe to rerun.
   - Duplicate suppression uses `disclosure_id + notification_type + channel + destination`.
   - Rerunning should not resend the same notification unless the dedupe key changes.

Tables that already assume upsert or dedupe behavior:

- `disclosures`
- `pdf_files`
- `guidance_revisions`
- `dividend_revisions`
- `financial_reports`
- `analysis_results`
- `valuation_views`
- `notifications`

## Failure Triage

When something stops, check in this order:

1. `/jobs`
   - Confirm which job last failed.
   - Check latest start/end times and the short error message.
2. `logs/pipeline.log`
   - `run_pipeline` prints timestamped `[run]`, `[ok]`, `[warn]`, and `[stop]` lines.
   - This is the fastest way to see whether the pipeline continued after a non-fatal failure.
3. `/notifications`
   - Confirm whether the pipeline reached the notification step.
4. `/disclosures/{id}`
   - For one affected disclosure, inspect PDF status, parse status, analysis result, and valuation view.

Useful failure patterns:

- Disclosure fetch failed:
  - Pipeline stops early.
  - Fix source-side issue and rerun `python -m scripts.run_pipeline`.
- PDF download failed:
  - Later jobs may still run, but PDF-dependent extraction can remain missing.
  - Fix manifest or resolver input, then rerun `python -m scripts.run_pdf_download` or the whole pipeline.
- Financial report extraction failed:
  - Check PDF parse status and supported-format assumptions.
  - Rerun `python -m scripts.run_financial_report_extraction` after fixing the parser or input.
- Notifications not sent:
  - Check `should_notify` in analysis, then check notification dedupe and channel settings.
  - Rerun `python -m scripts.run_notifications`.

## Failure Summary Report

Use the CLI report below to see where failures are concentrated before changing parsers or comparison logic:

```powershell
python -m scripts.report_failure_summary
```

This report aggregates:

- `comparison_error_reason`
  - grouped across `yoy`, `qoq`, and `average_progress`
- `pdf_files.parse_error_code` / `pdf_files.parse_error_message`
  - grouped only for `parse_status=FAILED`, with `parse_error_code` preferred for stable aggregation

Typical use:

- if `insufficient_history` dominates, improve historical reference coverage later
- if `scope_mismatch` or `cumulative_mismatch` dominates, inspect period/scope判定 first
- if `unsupported_format` dominates on PDF parse failures, expand supported PDF formats before tuning downstream logic

## Manual Recovery

Basic recovery rule: restart from the earliest affected stage, not from the end.

Recommended manual recovery steps:

1. Look at `/jobs` and identify the first failed job in the chain.
2. If the failure was in source ingestion, rerun from that job:

```powershell
python -m scripts.run_disclosure_fetch --source dummy --input data/samples/disclosures_sample.json
```

3. If disclosures are present but classification is stale, rerun:

```powershell
python -m scripts.reclassify_disclosures
```

4. If PDF states are missing or failed, rerun:

```powershell
python -m scripts.run_pdf_download --source dummy --manifest data/samples/pdf_links_sample.json
```

5. If revision extraction failed, rerun:

```powershell
python -m scripts.run_revision_extraction --source dummy --manifest data/samples/revision_extractions_sample.json
```

6. If earnings extraction failed, rerun:

```powershell
python -m scripts.run_financial_report_extraction --source dummy --manifest data/samples/financial_reports_sample.json
```

7. If comparison, valuation, or notification output looks stale, rerun the downstream chain:

```powershell
python -m scripts.run_financial_comparisons
python -m scripts.run_valuation_views
python -m scripts.run_notifications
```

8. If you are unsure, rerun the full pipeline:

```powershell
python -m scripts.run_pipeline
```

Do not manually delete rows unless the schema changed. For normal operational failures, rerun is the default recovery action.

## Minimal Operations Checklist

For personal daily operation, keep this checklist short:

1. Open `/jobs` and confirm the latest pipeline-related jobs are not `失敗`.
2. Confirm the latest `fetch_disclosures` time is recent enough for your schedule.
3. Open `/notifications` and confirm new alerts are appearing when expected.
4. If something looks stale, rerun `python -m scripts.run_pipeline`.
5. If one step keeps failing, inspect that job's error message first before touching the DB.

## Daily Operations

Use this fixed order every day:

1. Open `/jobs`.
   - Confirm `fetch_disclosures` succeeded recently.
   - Confirm `run_pdf_download`, `run_financial_report_extraction`, `run_financial_comparisons`, and `run_notifications` are not failing repeatedly.
2. Open `/notifications`.
   - Confirm new alerts are appearing when expected.
   - Confirm there are no obvious duplicate sends or broken message bodies.
3. Open `/disclosures`.
   - Confirm new disclosures are flowing in.
   - Spot-check that category labels look reasonable.
4. Run the failure summary.

```powershell
python -m scripts.report_failure_summary
```

5. If `unsupported_format` is high, inspect samples directly.

```powershell
python -m scripts.report_pdf_failure_samples --code unsupported_format --limit 10
```

If anything looks stale and you are not sure where it failed, rerun:

```powershell
python -m scripts.run_pipeline
```

## Weekly Operations

Use this once or twice per week:

1. Create a SQLite backup.

```powershell
python -m scripts.backup_sqlite
```

2. Check PDF storage usage.

```powershell
python -m scripts.manage_pdf_storage
```

3. If orphan PDFs have accumulated, clean them after review.

```powershell
python -m scripts.manage_pdf_storage --delete-orphans --older-than-days 7
```

4. Review the failure summary trend.
   - Is `unsupported_format` still the top parse issue?
   - Are `scope_mismatch` or `cumulative_mismatch` increasing?
   - Are notifications becoming noisy or too quiet?

## How To Read Failure Summary

Use the report to decide what to fix next, not to inspect every single failure.

- `parse_error_code`
  - Start with the most frequent code.
  - If `unsupported_format` is dominant, inspect samples before adding parser coverage.
  - If `period_detection_failed`, `scope_detection_failed`, or `cumulative_type_detection_failed` are dominant, improve extraction logic before expanding formats.
- `comparison_error_reason`
  - `insufficient_history` is often expected for newer coverage.
  - `q1_qoq_not_applicable` is usually normal and should not be treated as a bug.
  - `scope_mismatch`, `cumulative_mismatch`, and `extraction_confidence_low` are better improvement targets.

Recommended priority:

1. Failures that stop upstream flow (`fetch_disclosures`, PDF download, notification dispatch)
2. The most frequent `parse_error_code`
3. The most frequent actionable `comparison_error_reason`
4. Only then UI wording or additional analysis features

## First 3 To 7 Days Of Real Operation

During the first 3 to 7 days, focus on trend and concentration, not polish.

Check these points every day:

1. Are new disclosures entering the system consistently?
2. Are PDF downloads mostly succeeding?
3. Is one `parse_error_code` clearly dominating?
4. Is one `comparison_error_reason` clearly dominating?
5. Are should-notify cases missing, or are duplicate notifications happening?
6. Are unsupported samples clustering around one common pattern?

Do not add broad new features during this period.

Use this rule:

- If one failure code is clearly the largest bucket, fix that bucket first.
- If failure volume is low and scattered, keep observing before changing parser logic.
- If notifications are wrong, fix correctness before improving message style.

## SQLite Backup

Keep backup simple. For a small VPS MVP, a file-level SQLite backup is enough if you do it regularly.

Recommended policy:

- Keep backups under `data/backups`.
- Create at least one backup per day.
- Keep the latest 7 backups for normal personal operation.
- Take a manual backup before schema recreation or risky parser changes.

Create a backup:

```powershell
python -m scripts.backup_sqlite
```

Optional retention override:

```powershell
python -m scripts.backup_sqlite --backup-dir data/backups --keep 14
```

This script uses SQLite's backup API, so it is safer than copying the DB file blindly while the app may still be reading or writing.

## PDF Storage Capacity Management

Keep PDF management conservative. The MVP should not delete referenced files automatically.

Recommended policy:

- Store PDFs only under `data/pdf`.
- Treat files referenced by `pdf_files.file_path` as active.
- Treat unreferenced files as orphan candidates.
- Do not delete recent orphan files automatically.
- Review storage regularly and delete only orphan files older than a safe threshold.

Inspect storage in dry-run mode:

```powershell
python -m scripts.manage_pdf_storage
```

Delete orphan PDFs older than 7 days:

```powershell
python -m scripts.manage_pdf_storage --delete-orphans --older-than-days 7
```

The dry-run output shows:

- total PDF file count
- total PDF size
- referenced PDF count and size
- orphan PDF count and size
- a sample list of orphan files

## Old PDF and Unnecessary File Policy

Use this simple rule set:

1. Referenced PDFs are not deleted by cleanup.
2. Orphan PDFs can be deleted after they are older than 7 days.
3. Failed downloads with no local file are left as DB state only and do not affect disk usage.
4. If you change schema or reset the environment, remove only files you know are test data or orphaned artifacts.

Do not bulk-delete `data/pdf` unless you are intentionally rebuilding the local cache.

## Capacity and Backup Checklist

For weekly maintenance on a small VPS:

1. Run `python -m scripts.backup_sqlite`.
2. Run `python -m scripts.manage_pdf_storage` and check orphan size.
3. If orphan files have accumulated, run cleanup with `--delete-orphans --older-than-days 7`.
4. Confirm free disk space is still comfortable after cleanup.
5. Before model/schema changes, create a fresh SQLite backup first.

## API

- `GET /health` : health check

## Notes

- This repository currently includes only the foundation layer.
- Disclosure ingestion is currently wired through a dummy fetcher for local testing.
- PDF download is currently wired through a dummy manifest-based resolver for local testing.
- Revision extraction is currently wired through a dummy manifest-based extractor for local testing.
- Financial report extraction currently supports a narrow dummy tabular summary format for earnings-report PDFs (`dummy.tabular_summary_v1`, `dummy.tabular_summary_v2`, `dummy.tabular_summary_v3`, and `dummy.tabular_summary_v4`). Unsupported format expansion is intentionally paused here; further parser coverage should be driven by real failure-summary frequency.
- MVP parser scope is intentionally limited to earnings PDFs that can be mapped to a stable table summary format.
- Comparison logic currently uses a narrow reference key: same company, comparable period, scope, cumulative type, and accounting standard, then falls back to explicit mismatch reasons.
- `analysis_results` is now treated as the interpretation table. It distinguishes `unchanged_detected`, `no_revision_detected`, and directional revision detection for guidance/dividend.
- The current summary is template-based and Japanese-oriented for notifications and mobile UI.
- `auto_summary` is kept short for notification use. The summary builder also supports a longer standard-form sentence structure for future detail screens.
- If `companies.name_ja` is populated, UI and notifications prefer the Japanese company name over the fallback name field.
- UI formatting rounds scores and rates for readability. Stored values remain unchanged in SQLite.
- `valuation_views` is generated from `analysis_results` as a conservative hypothesis layer, not as a price-screening or price-prediction feature.
- Notifications use `disclosure_id + notification_type + channel + destination` as the dedupe key, and they can run in `dummy` mode or `telegram` mode.
- UI currently exposes two lightweight server-rendered pages: `/disclosures` and `/disclosures/{id}`. The notification detail URL should point to `/disclosures/{id}`.
- Additional lightweight operations views are available at `/notifications` and `/jobs` for notification history and latest job health checks.
- `job_runs` stores `processed_count` plus `result_summary_json` when a job returns a dict. `/jobs` shows only a short summary of the most useful counters.
- Daily cron operation should use the single serial pipeline entry point `python -m scripts.run_pipeline` instead of registering each job separately.
- If you change SQLAlchemy models, recreate the SQLite DB because migrations are not implemented yet.
- SQLite is used by default and the DB file is created under `data/app.db`.

## Job Runner Example

```python
from app.jobs.runner import run_job

def sample_job(context):
    context.set_processed_count(1)
    return {"status": "ok"}

run_job("sample_job", sample_job)
```


## PDF Failure Samples Report

Use the CLI below to inspect representative failed PDF parse samples by `parse_error_code`:

```powershell
python -m scripts.report_pdf_failure_samples
```

Filter to one code and show the top 10 samples:

```powershell
python -m scripts.report_pdf_failure_samples --code unsupported_format --limit 10
```

Typical use:

- find which `parse_error_code` is most common before changing parser logic
- inspect `disclosure_id`, company, title, and `file_path` for quick sample collection
- use `parse_error_message` as the human-readable hint, but prioritize `parse_error_code` for stable grouping





## JPX TDnet Fetcher

The fixed production disclosure source is JPX Company Announcements Disclosure Service (TDnet browser pages).

Implementation choice:

- provider is fixed to JPX TDnet
- the actual list URL is supplied as a template because the public JPX UI is JavaScript-driven
- the template must accept `{date}` in `YYYY-MM-DD` format
- the fetcher is designed for full-market ingestion first, then downstream active/analysis filtering

Recommended environment variable:

```env
JPX_DISCLOSURE_URL_TEMPLATE=https://example.com/jpx/disclosures?date={date}
```

CLI examples:

Fetch today in JST:

```powershell
python -m scripts.run_disclosure_fetch --source jpx-tdnet --url-template "https://example.com/jpx/disclosures?date={date}"
```

Fetch one day explicitly:

```powershell
python -m scripts.run_disclosure_fetch --source jpx-tdnet --url-template "https://example.com/jpx/disclosures?date={date}" --date 2026-03-16
```

Fetch a date range:

```powershell
python -m scripts.run_disclosure_fetch --source jpx-tdnet --url-template "https://example.com/jpx/disclosures?date={date}" --date-from 2026-03-14 --date-to 2026-03-16
```

Pipeline example with JPX TDnet source:

```powershell
python -m scripts.run_pipeline --disclosure-source jpx-tdnet --disclosure-url-template "https://example.com/jpx/disclosures?date={date}"
```

15-minute cron example:

```cron
*/15 * * * * cd /srv/disclosure-fundamental-mvp && JPX_DISCLOSURE_URL_TEMPLATE="https://example.com/jpx/disclosures?date={date}" /srv/disclosure-fundamental-mvp/.venv/bin/python -m scripts.run_pipeline >> /srv/disclosure-fundamental-mvp/logs/pipeline.log 2>&1
```

Re-fetch procedure:

- same-day retry: rerun `run_disclosure_fetch` for today or rerun the full pipeline
- historical retry: use `--date` or `--date-from/--date-to`
- dedupe still relies on `source_disclosure_id` first, then `source_name + company_id + disclosed_at + title`
- unknown company codes are no longer rejected at ingest time; a stub inactive company row is created and the disclosure is still saved

## JPX TDnet Production Hardening

Recommended real-source production settings:

```env
JPX_DISCLOSURE_URL_TEMPLATE=https://www.jpx.co.jp/path/to/disclosure-list?date={date}
```

The production fetcher behavior is now explicit:

- HTTP timeout is configurable
- retry count is configurable
- a User-Agent is always sent
- `source_disclosure_id` is normalized from the absolute disclosure URL
  - lower-cased scheme and host
  - fragment removed
  - query parameters sorted for stable dedupe
- zero results are classified as one of:
  - `normal_zero`
  - `structure_anomaly_zero`

Expected HTML structure:

- at least one `<table>` exists
- disclosure rows are represented by `<tr>` with at least 3 `<td>` cells
- a row should contain:
  - time text such as `15:00`
  - company code
  - company name
  - title, usually through an `<a href="...">` element

Normal zero means:

- the page has a table
- there are no data rows for the requested day

Structure anomaly zero means:

- no table exists, or
- data rows exist but no valid disclosure record can be extracted

Smoke fetch commands:

One-day smoke fetch:

```powershell
python -m scripts.run_disclosure_fetch --source jpx-tdnet --url-template "https://www.jpx.co.jp/path/to/disclosure-list?date={date}" --date 2026-03-16 --timeout 30 --retry-count 2
```

Range smoke fetch:

```powershell
python -m scripts.run_disclosure_fetch --source jpx-tdnet --url-template "https://www.jpx.co.jp/path/to/disclosure-list?date={date}" --date-from 2026-03-14 --date-to 2026-03-16 --timeout 30 --retry-count 2
```

Pipeline example:

```powershell
python -m scripts.run_pipeline --disclosure-source jpx-tdnet --disclosure-url-template "https://www.jpx.co.jp/path/to/disclosure-list?date={date}"
```

Failure log examples:

- normal zero:
  - `JPX fetch date=2026-03-16 status=normal_zero tables=1 rows=1 data_rows=0 extracted=0 url=...`
- structure anomaly:
  - `JPX fetch date=2026-03-16 status=structure_anomaly_zero tables=0 rows=0 data_rows=0 extracted=0 url=...`
  - followed by `ValueError: JPX disclosure HTML structure anomaly for 2026-03-16: no_table_found`

Re-fetch confirmation procedure:

1. run one-day fetch for a known date
2. confirm insert count on the first run
3. rerun the same date
4. confirm duplicate count does not increase because `source_disclosure_id` is normalized and stable
5. check `/jobs` and `/disclosures` after rerun

Because this execution environment does not have unrestricted outbound network access, the real JPX one-day smoke fetch was prepared and validated at the parser/test level, but final live verification must be run on Lightsail or another network-enabled host using the commands above.
