"""FastAPI backend + dashboard for the Pakistan Health Atlas."""
import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Literal

from paths import CHARTS, CSV, DATA, RAW, REJECTED, REPORT, STATIC
from step1_fetch import PROVINCES, fetch_all_provinces
from step2_clean import clean_and_validate
from step3_database import (
    count_from_database, dashboard_summary, fetch_from_database,
    init_database, save_to_database,
)
from step4_eda import generate_readme, run_eda

app = FastAPI(title="Pakistan Health Atlas", version="1.0.0", description="OSM-powered health facility ETL, EDA and dashboard")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="health-atlas-pipeline")
_lock = threading.Lock()
_job = None


def _time():
    return datetime.now(timezone.utc).isoformat()


def _job_update(**changes):
    global _job
    with _lock:
        if _job is not None:
            _job = {**_job, **changes}


def _execute_job(action, province):
    """Run jobs in a worker so the interface stays responsive while fetching."""
    try:
        results = {}
        if action in {"fetch", "all"}:
            _job_update(stage="Downloading OpenStreetMap data", progress=4)

            def on_region(message, done, total):
                _job_update(stage=message, progress=5 + int(58 * done / max(total, 1)))

            fetched = fetch_all_provinces(province, progress=on_region)
            results["fetch"] = fetched
            _job_update(progress=63, stage="Data download complete")

        if action in {"clean", "all"}:
            _job_update(stage="Cleaning and validating facilities", progress=67 if action == "all" else 15)
            valid, _rejected, clean_summary = clean_and_validate(province)
            _job_update(stage="Saving validated facilities to SQLite", progress=80 if action == "all" else 65)
            saved = save_to_database(valid)
            results["clean"] = clean_summary
            results["database"] = saved

        if action in {"analyze", "all"}:
            _job_update(stage="Generating analysis and charts", progress=88 if action == "all" else 35)
            eda = run_eda()
            if "message" in eda:
                raise ValueError(eda["message"])
            results["analysis"] = {"total_valid_facilities": eda["total_valid_facilities"]}

        if action in {"report", "all"}:
            _job_update(stage="Writing findings report", progress=96 if action == "all" else 55)
            results["report"] = generate_readme()

        warnings = [f"{item['province']}: {item.get('error', 'Download failed')}"
                    for item in results.get('fetch', []) if item.get('status') == 'failed']
        _job_update(status="completed_with_warnings" if warnings else "completed",
                    stage="Finished with some download failures" if warnings else "Completed successfully",
                    progress=100, result=results, warnings=warnings, finished_at=_time())
    except Exception as exc:
        _job_update(status="failed", stage="An error occurred", error=str(exc), finished_at=_time())


class JobRequest(BaseModel):
    action: Literal["fetch", "clean", "analyze", "report", "all"]
    province: str | None = None


@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(STATIC / "index.html")


@app.get("/api/regions")
def regions():
    return [{"key": k, "name": value[0]} for k, value in PROVINCES.items()]


@app.get("/api/summary")
def summary():
    return dashboard_summary()


@app.get("/api/status")
def status():
    cached = sorted(p.stem for p in RAW.glob("*.json") if p.stem in PROVINCES)
    with _lock:
        active = dict(_job) if _job else None
    return {
        "raw_regions": cached,
        "raw_count": len(cached),
        "csv_available": CSV.exists(),
        "report_available": REPORT.exists(),
        "charts_available": all((CHARTS / name).exists() for name in
                                ("facility_types.png", "public_vs_private.png", "province_per_100k.png")),
        "job": active,
    }


@app.post("/api/jobs", status_code=202)
def start_job(payload: JobRequest):
    global _job
    if payload.province and payload.province not in PROVINCES:
        raise HTTPException(422, f"Unknown region: {payload.province}")
    with _lock:
        if _job and _job["status"] in {"queued", "running"}:
            raise HTTPException(409, "A pipeline task is already running")
        _job = {
            "id": uuid4().hex, "action": payload.action, "province": payload.province,
            "status": "running", "stage": "Preparing task", "progress": 0,
            "error": None, "result": None, "warnings": [], "started_at": _time(), "finished_at": None,
        }
        current = dict(_job)
    try:
        _executor.submit(_execute_job, payload.action, payload.province)
    except RuntimeError as exc:
        _job_update(status="failed", error=str(exc), finished_at=_time())
        raise HTTPException(503, "Pipeline worker unavailable") from exc
    return current


@app.get("/api/jobs/current")
def current_job():
    with _lock:
        return {"job": dict(_job) if _job else None}


# Backward-compatible API for scripts; web frontend uses async background jobs.
@app.post("/fetch")
def api_fetch(province: str | None = None):
    if province and province not in PROVINCES:
        raise HTTPException(422, "Invalid region")
    try:
        return {"downloaded": fetch_all_provinces(province)}
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/clean-and-save")
def api_clean_and_save(province: str | None = None):
    try:
        valid, _, clean = clean_and_validate(province)
        saved = save_to_database(valid)
        return {"cleaning": clean, "database": saved}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/run-all")
def api_run_all(province: str | None = None):
    if province and province not in PROVINCES:
        raise HTTPException(422, "Invalid region")
    try:
        fetched = fetch_all_provinces(province)
        valid, _, clean = clean_and_validate(province)
        db = save_to_database(valid)
        eda = run_eda()
        report = generate_readme()
        return {"step1_fetch": fetched, "step2_clean": clean, "step3_database": db,
                "step4_eda_total": eda.get("total_valid_facilities"), "step5_readme": report}
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/facilities")
def api_facilities(
    province: str | None = None,
    facility_type: str | None = None,
    ownership: str | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(12, ge=1, le=200),
    page: int = Query(1, ge=1),
):
    total = count_from_database(province, facility_type, ownership, q)
    rows = fetch_from_database(province, facility_type, ownership, limit, q, page)
    return {"count": len(rows), "total": total, "page": page, "limit": limit,
            "pages": max(1, math.ceil(total / limit)), "facilities": rows}


@app.get("/rejected")
def api_rejected(limit: int = Query(50, ge=1, le=1000)):
    if not REJECTED.exists():
        return {"total_rejected": 0, "items": []}
    try:
        with REJECTED.open("r", encoding="utf-8") as fh:
            records = json.load(fh)
    except (OSError, ValueError) as exc:
        raise HTTPException(500, "Rejected-data file is unreadable") from exc
    return {"total_rejected": len(records), "items": records[:limit]}


@app.get("/eda")
def api_eda():
    return run_eda()


@app.post("/make-readme")
def api_make_readme():
    try:
        return generate_readme()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/download-csv")
def download_csv():
    if not CSV.is_file():
        raise HTTPException(404, "No CSV yet. Run the cleaning step first.")
    return FileResponse(str(CSV), media_type="text/csv", filename="pakistan_health_clean.csv")


@app.get("/download-report")
def download_report():
    if not REPORT.is_file():
        raise HTTPException(404, "No report yet. Run analysis and report generation.")
    return FileResponse(str(REPORT), media_type="text/markdown", filename="Pakistan_Health_Report.md")


@app.get("/charts/{chart_name}")
def get_chart(chart_name: str):
    allowed = {"facility_types.png", "public_vs_private.png", "province_per_100k.png"}
    if chart_name not in allowed:
        raise HTTPException(404, "Chart not found")
    filename = CHARTS / chart_name
    if not filename.is_file():
        raise HTTPException(404, "No chart yet. Run analysis first.")
    return FileResponse(str(filename), media_type="image/png")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
