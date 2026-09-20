"""Persistenza dei job di screenshot su SQLite.

Ogni operazione apre e chiude la propria connessione al file: per il volume di
scrittura di questo servizio (contenuto dal rate limit e dal semaforo di
concorrenza) è sufficiente, senza dover gestire una connessione condivisa tra
le coroutine. I metodi pubblici sono async solo per spostare la parte
bloccante (I/O su disco) in un thread — asyncio.to_thread, stesso pattern già
usato in app/security.py per la risoluzione DNS.
"""

import asyncio
import sqlite3
from pathlib import Path

from app.config import DB_PATH


class JobsDatabase:
    """Gestisce la persistenza dei job di screenshot su un file SQLite."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                full_page INTEGER NOT NULL,
                dark_mode INTEGER NOT NULL,
                block_ads INTEGER NOT NULL,
                status TEXT NOT NULL,
                filename TEXT,
                error TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        return conn

    def _insert(self, row: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs
                    (id, url, width, height, full_page, dark_mode, block_ads, status, filename, error, created_at)
                VALUES
                    (:id, :url, :width, :height, :full_page, :dark_mode, :block_ads, :status, :filename, :error, :created_at)
                """,
                row,
            )

    def _select_one(self, job_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def _select_many(self, limit: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def _update(self, job_id: str, fields: dict) -> None:
        assignments = ", ".join(f"{key} = :{key}" for key in fields)
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {assignments} WHERE id = :id", {**fields, "id": job_id})

    def clear_all_sync(self) -> None:
        """Svuota la tabella dei job. Versione sincrona, usata solo dai test."""
        with self._connect() as conn:
            conn.execute("DELETE FROM jobs")

    async def insert(self, row: dict) -> None:
        """Inserisce un nuovo job."""
        await asyncio.to_thread(self._insert, row)

    async def select_one(self, job_id: str) -> dict | None:
        """Recupera un job per id, o None se non esiste."""
        return await asyncio.to_thread(self._select_one, job_id)

    async def select_many(self, limit: int) -> list[dict]:
        """Recupera i job più recenti, dal più recente al più vecchio."""
        return await asyncio.to_thread(self._select_many, limit)

    async def update(self, job_id: str, **fields) -> None:
        """Aggiorna uno o più campi di un job esistente."""
        await asyncio.to_thread(self._update, job_id, fields)


db = JobsDatabase()
