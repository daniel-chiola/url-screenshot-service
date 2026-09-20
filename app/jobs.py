"""Coda in-memory dei job di screenshot: creazione, stato e processamento in background."""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import MAX_CONCURRENT_CAPTURES, SCREENSHOTS_DIR
from app.screenshot import capture_screenshot
from app.utils import is_reachable, url_to_filename

logger = logging.getLogger(__name__)

_capture_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CAPTURES)
_jobs: dict[str, "Job"] = {}


@dataclass
class Job:
    """Stato di un job di cattura screenshot."""

    id: str
    url: str
    width: int = 1280
    height: int = 800
    full_page: bool = False
    dark_mode: bool = False
    block_ads: bool = True
    status: str = "pending"  # pending | processing | done | error
    filename: str | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def create_job(
    url: str,
    width: int = 1280,
    height: int = 800,
    full_page: bool = False,
    dark_mode: bool = False,
    block_ads: bool = True,
) -> Job:
    """Crea e registra un nuovo job in stato 'pending'."""
    job = Job(
        id=str(uuid.uuid4()),
        url=url,
        width=width,
        height=height,
        full_page=full_page,
        dark_mode=dark_mode,
        block_ads=block_ads,
    )
    _jobs[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    """Recupera un job per id, o None se non esiste."""
    return _jobs.get(job_id)


def list_jobs(limit: int = 50) -> list[Job]:
    """Elenca i job più recenti, dal più recente al più vecchio."""
    return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]


async def process_job(job_id: str) -> None:
    """Esegue la verifica di raggiungibilità e la cattura per un job, aggiornandone lo stato."""
    job = _jobs[job_id]
    job.status = "processing"

    if not await is_reachable(job.url):
        job.status = "error"
        job.error = "URL non raggiungibile"
        logger.warning("Job %s: URL non raggiungibile (%s)", job_id, job.url)
        return

    filename = url_to_filename(job.url)
    output_path = os.path.join(SCREENSHOTS_DIR, filename)

    async with _capture_semaphore:
        try:
            await capture_screenshot(
                job.url,
                output_path,
                width=job.width,
                height=job.height,
                full_page=job.full_page,
                dark_mode=job.dark_mode,
                block_ads=job.block_ads,
            )
        except Exception as e:
            job.status = "error"
            job.error = str(e)
            logger.error("Job %s: errore durante la cattura (%s)", job_id, e)
            return

    job.filename = filename
    job.status = "done"
    logger.info("Job %s: completato (%s)", job_id, filename)
