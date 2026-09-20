"""API REST che riceve un URL, accoda una cattura screenshot in background e ne espone lo stato."""

import logging
import os
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app import jobs
from app.config import RATE_LIMIT, SCREENSHOTS_DIR
from app.jobs import Job
from app.schemas import JobDetail, JobResponse, ScreenshotRequest
from app.security import is_safe_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="URL Screenshot Service")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def _to_detail(job: Job) -> JobDetail:
    return JobDetail(
        id=job.id,
        url=job.url,
        status=job.status,
        filename=job.filename,
        error=job.error,
        created_at=job.created_at,
    )


@app.get("/health")
def health() -> dict:
    """Dice se il servizio è attivo (usato per i controlli di stato automatici)."""
    return {"status": "ok"}


@app.post("/screenshot", response_model=JobResponse, status_code=202)
@limiter.limit(RATE_LIMIT)
async def submit_screenshot(
    request: Request, payload: ScreenshotRequest, background_tasks: BackgroundTasks
) -> JobResponse:
    """Accoda la cattura di uno screenshot e torna subito l'id del job."""
    url = str(payload.url)
    if not await is_safe_url(url):
        logger.warning("URL bloccato (protezione SSRF): %s", url)
        raise HTTPException(status_code=403, detail="URL non consentito (indirizzo privato o riservato)")

    job = jobs.create_job(
        url,
        width=payload.width,
        height=payload.height,
        full_page=payload.full_page,
        dark_mode=payload.dark_mode,
        block_ads=payload.block_ads,
    )
    background_tasks.add_task(jobs.process_job, job.id)
    return JobResponse(id=job.id, status=job.status)


@app.get("/screenshot/{job_id}", response_model=JobDetail)
def get_screenshot_status(job_id: str) -> JobDetail:
    """Stato di un job di screenshot."""
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job non trovato")
    return _to_detail(job)


@app.get("/jobs", response_model=list[JobDetail])
def list_jobs() -> list[JobDetail]:
    """Coda dei job, dal più recente al più vecchio."""
    return [_to_detail(job) for job in jobs.list_jobs()]


app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
