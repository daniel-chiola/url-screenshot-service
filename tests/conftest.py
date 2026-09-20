"""Fixture condivise da tutti i test.

Una "fixture" in pytest è una funzione che prepara qualcosa prima di un test
(e, se serve, lo ripulisce dopo). Basta metterla come parametro di un test per
usarla: pytest la esegue automaticamente e passa il risultato.
"""

import os
import tempfile

# app.config legge SCREENSHOTS_DIR al momento dell'import (default "/app/screenshots",
# pensato per il container). Va impostata PRIMA di importare qualsiasi cosa da "app",
# altrimenti fuori da Docker os.makedirs fallisce (filesystem non scrivibile).
os.environ.setdefault("SCREENSHOTS_DIR", os.path.join(tempfile.gettempdir(), "url-screenshot-service-tests"))

import pytest

from app import jobs
from app.main import limiter


@pytest.fixture
def anyio_backend():
    """Dice al plugin anyio di usare asyncio per eseguire i test 'async def'."""
    return "asyncio"


@pytest.fixture(autouse=True)
def clear_jobs():
    """Svuota la coda dei job prima (e dopo) ogni test.

    app/jobs.py tiene tutti i job in un dizionario a livello di modulo (_jobs),
    condiviso da tutto il programma mentre gira. Nei test è un problema: se un
    test crea un job e non lo ripulisce, quel job resta visibile anche nei test
    successivi, che quindi falliscono (o peggio, passano per caso) a seconda
    dell'ordine in cui pytest li esegue.

    `autouse=True` fa sì che questa fixture parta da sola prima di OGNI test,
    senza doverla nominare esplicitamente in ciascuno.
    """
    jobs._jobs.clear()
    yield
    jobs._jobs.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Azzera i contatori del rate limit prima di ogni test.

    Stesso problema di clear_jobs: il rate limit (slowapi) tiene il conteggio
    delle richieste in uno stato condiviso da tutta l'app. Senza reset, un test
    che fa più richieste a POST /screenshot farebbe salire il contatore anche
    per i test successivi, facendoli fallire con 429 in modo imprevedibile.
    """
    limiter.reset()
    yield
    limiter.reset()
