"""FastAPI dashboard: start an audit, watch it run, browse results, and
download the report as HTML or PDF."""
import json
import threading
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from seoscope import db
from seoscope.auditor import execute_audit
from seoscope.config import DEFAULT_MAX_PAGES, MAX_MAX_PAGES
from seoscope.pdf import html_to_pdf
from seoscope.roadmap import build_roadmap
from seoscope.scoring import grade_for_score

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="SEOScope")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["grade"] = grade_for_score

# In-memory progress log per running audit_id, so the dashboard can poll
# status without needing a websocket or task queue for a single-user local tool.
_progress: dict[int, list[str]] = {}
_progress_lock = threading.Lock()


@app.on_event("startup")
def startup():
    db.init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    audits = db.list_audits()
    return templates.TemplateResponse("index.html", {
        "request": request, "audits": audits, "default_max_pages": DEFAULT_MAX_PAGES,
        "max_max_pages": MAX_MAX_PAGES,
    })


@app.post("/audits")
def start_audit(url: str = Form(...), max_pages: int = Form(DEFAULT_MAX_PAGES)):
    max_pages = max(1, min(max_pages, MAX_MAX_PAGES))

    def on_progress(audit_id, message):
        with _progress_lock:
            _progress.setdefault(audit_id, []).append(message)

    # Create the audit row up front (so the browser can redirect to its
    # dashboard immediately) and run the actual crawl in a background
    # thread, since a full audit can take much longer than one HTTP request.
    audit_id = db.create_audit(url, max_pages)

    def worker():
        try:
            execute_audit(audit_id, url, max_pages,
                           progress_cb=lambda msg: on_progress(audit_id, msg))
        except Exception as exc:  # noqa: BLE001 - already recorded on the audit row
            pass

    threading.Thread(target=worker, daemon=True).start()

    return RedirectResponse(url=f"/audits/{audit_id}", status_code=303)


@app.get("/audits/{audit_id}/status")
def audit_status(audit_id: int):
    audit = db.get_audit(audit_id)
    if not audit:
        return {"status": "not_found"}
    with _progress_lock:
        log = list(_progress.get(audit_id, []))
    return {"status": audit["status"], "log": log[-20:], "error": audit.get("error")}


@app.get("/audits/{audit_id}", response_class=HTMLResponse)
def audit_dashboard(request: Request, audit_id: int):
    audit = db.get_audit(audit_id)
    if not audit:
        return HTMLResponse("Audit not found", status_code=404)

    if audit["status"] == "running":
        return templates.TemplateResponse("running.html", {"request": request, "audit": audit})

    return templates.TemplateResponse("dashboard.html", _dashboard_context(request, audit))


def _dashboard_context(request: Request, audit: dict) -> dict:
    issues = db.get_issues(audit["id"])
    pages = db.get_pages(audit["id"])
    category_scores = json.loads(audit["category_scores"]) if audit.get("category_scores") else {}
    roadmap = build_roadmap(issues)

    severity_counts = {"critical": 0, "warning": 0, "info": 0}
    for issue in issues:
        severity_counts[issue["severity"]] = severity_counts.get(issue["severity"], 0) + issue.get("affected_count", 1)

    return {
        "request": request, "audit": audit, "issues": issues, "pages": pages,
        "category_scores": category_scores, "roadmap": roadmap,
        "severity_counts": severity_counts,
    }


@app.get("/audits/{audit_id}/report.html", response_class=HTMLResponse)
def audit_report_html(request: Request, audit_id: int):
    audit = db.get_audit(audit_id)
    if not audit or audit["status"] != "completed":
        return HTMLResponse("Audit not available", status_code=404)
    context = _dashboard_context(request, audit)
    return templates.TemplateResponse("report.html", context)


@app.get("/audits/{audit_id}/report.pdf")
def audit_report_pdf(request: Request, audit_id: int):
    audit = db.get_audit(audit_id)
    if not audit or audit["status"] != "completed":
        return HTMLResponse("Audit not available", status_code=404)
    context = _dashboard_context(request, audit)
    html = templates.get_template("report.html").render(context)
    pdf_bytes = html_to_pdf(html)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="seoscope-audit-{audit_id}.pdf"'
    })


@app.post("/audits/{audit_id}/delete")
def delete_audit(audit_id: int):
    db.delete_audit(audit_id)
    return RedirectResponse(url="/", status_code=303)
