from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.services.disclosure_view_service import (
    category_label,
    company_display_name,
    comparison_label,
    cumulative_type_label,
    download_status_label,
    format_datetime,
    format_decimal,
    format_score,
    format_text,
    get_disclosure_detail,
    job_status_label,
    list_recent_disclosures,
    list_job_statuses,
    list_notifications,
    notification_status_label,
    parse_status_label,
    period_type_label,
    priority_label,
    revision_detection_label,
    revision_direction_label,
    statement_scope_label,
    tone_label,
    yes_no_label,
)


settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    return RedirectResponse(url="/disclosures", status_code=302)


@app.get("/disclosures", response_class=HTMLResponse)
def disclosures_index(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    disclosures = list_recent_disclosures(session)
    return templates.TemplateResponse(
        request,
        "disclosures_index.html",
        {"request": request, "disclosures": disclosures},
    )


@app.get("/disclosures/{disclosure_id}", response_class=HTMLResponse)
def disclosure_detail(
    disclosure_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    disclosure = get_disclosure_detail(session, disclosure_id)
    if disclosure is None:
        raise HTTPException(status_code=404, detail="Disclosure not found")

    return templates.TemplateResponse(
        request,
        "disclosure_detail.html",
        {
            "request": request,
            "disclosure": disclosure,
            "category_label": category_label,
            "company_display_name": company_display_name,
            "comparison_label": comparison_label,
            "cumulative_type_label": cumulative_type_label,
            "priority_label": priority_label,
            "download_status_label": download_status_label,
            "parse_status_label": parse_status_label,
            "notification_status_label": notification_status_label,
            "format_decimal": format_decimal,
            "format_score": format_score,
            "format_text": format_text,
            "format_datetime": format_datetime,
            "period_type_label": period_type_label,
            "revision_detection_label": revision_detection_label,
            "revision_direction_label": revision_direction_label,
            "statement_scope_label": statement_scope_label,
            "tone_label": tone_label,
            "yes_no_label": yes_no_label,
        },
    )


@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    notifications = list_notifications(session)
    return templates.TemplateResponse(
        request,
        "notifications.html",
        {"request": request, "notifications": notifications},
    )


@app.get("/jobs", response_class=HTMLResponse)
def jobs_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    jobs = list_job_statuses(session)
    return templates.TemplateResponse(
        request,
        "jobs.html",
        {"request": request, "jobs": jobs},
    )
