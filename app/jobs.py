"""Coda dei job di screenshot: creazione, stato e processamento in background.

I job sono persistiti su SQLite ([app/db.py](app/db.py)) invece che tenuti solo in
memoria: sopravvivono a un riavvio del container, e un job fallito può essere
recuperato con retry_job() invece di essere perso per sempre.
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import MAX_CONCURRENT_CAPTURES, SCREENSHOTS_DIR
from app.db import db
from app.screenshot import capture_screenshot
from app.utils import is_reachable, url_to_filename

logger = logging.getLogger(__name__)

_capture_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CAPTURES)


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

    @classmethod
    def _from_row(cls, row: dict) -> "Job":
        return cls(
            id=row["id"],
            url=row["url"],
            width=row["width"],
            height=row["height"],
            full_page=bool(row["full_page"]),
            dark_mode=bool(row["dark_mode"]),
            block_ads=bool(row["block_ads"]),
            status=row["status"],
            filename=row["filename"],
            error=row["error"],
            created_at=row["created_at"],
        )


async def create_job(
    url: str,
    width: int = 1280,
    height: int = 800,
    full_page: bool = False,
    dark_mode: bool = False,
    block_ads: bool = True,
) -> Job:
    """Crea e salva un nuovo job in stato 'pending'."""
    job = Job(
        id=str(uuid.uuid4()),
        url=url,
        width=width,
        height=height,
        full_page=full_page,
        dark_mode=dark_mode,
        block_ads=block_ads,
    )
    await db.insert(
        {
            "id": job.id,
            "url": job.url,
            "width": job.width,
            "height": job.height,
            "full_page": int(job.full_page),
            "dark_mode": int(job.dark_mode),
            "block_ads": int(job.block_ads),
            "status": job.status,
            "filename": job.filename,
            "error": job.error,
            "created_at": job.created_at,
        }
    )
    return job


async def get_job(job_id: str) -> Job | None:
    """Recupera un job per id, o None se non esiste."""
    row = await db.select_one(job_id)
    return Job._from_row(row) if row else None


async def list_jobs(limit: int = 50) -> list[Job]:
    """Elenca i job più recenti, dal più recente al più vecchio."""
    rows = await db.select_many(limit)
    return [Job._from_row(row) for row in rows]


async def count_jobs(status: str | None = None) -> int:
    """Conta i job, opzionalmente filtrati per stato."""
    return await db.count(status)


async def avg_seconds_to_completion() -> float | None:
    """Tempo medio (in secondi) impiegato dai job per arrivare a "done" o "error" (job ancora in coda esclusi)."""
    return await db.avg_seconds_to_completion()


async def retry_job(job_id: str) -> Job | None:
    """Rimette in coda un job in stato 'error'. None se non esiste o non è in errore."""
    job = await get_job(job_id)
    if job is None or job.status != "error":
        return None
    await db.update(job_id, status="pending", error=None, filename=None)
    return await get_job(job_id)


async def process_job(job_id: str) -> None:
    """Esegue la verifica di raggiungibilità e la cattura per un job, aggiornandone lo stato."""
    job = await get_job(job_id)
    if job is None:
        logger.error("Job %s: non trovato, impossibile processarlo", job_id)
        return

    await db.update(job_id, status="processing")

    if not await is_reachable(job.url):
        await db.update(job_id, status="error", error="URL non raggiungibile")
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
            await db.update(job_id, status="error", error=str(e))
            logger.error("Job %s: errore durante la cattura (%s)", job_id, e)
            return

    await db.update(job_id, status="done", filename=filename)
    logger.info("Job %s: completato (%s)", job_id, filename)
