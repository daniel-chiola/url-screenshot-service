"""Test per app/db.py (solo i percorsi non coperti indirettamente da test_jobs.py)."""

import os
import sqlite3
import tempfile

import pytest

from app.db import JobsDatabase

pytestmark = pytest.mark.anyio


def _crea_db_con_schema_vecchio(path: str) -> None:
    """Crea un file SQLite con lo schema precedente all'introduzione di updated_at."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY, url TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
            full_page INTEGER NOT NULL, dark_mode INTEGER NOT NULL, block_ads INTEGER NOT NULL,
            status TEXT NOT NULL, filename TEXT, error TEXT, created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO jobs VALUES ('id1','https://x.com',1280,800,0,0,1,'done','f.png',NULL,'2026-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()


async def test_connect_migra_un_db_senza_la_colonna_updated_at():
    """Un file SQLite creato prima di updated_at viene migrato automaticamente alla connessione."""
    path = os.path.join(tempfile.mkdtemp(), "vecchio.db")
    _crea_db_con_schema_vecchio(path)
    db = JobsDatabase(db_path=path)

    row = await db.select_one("id1")

    assert row["updated_at"] == "2026-01-01T00:00:00+00:00"  # va in backfill da created_at
