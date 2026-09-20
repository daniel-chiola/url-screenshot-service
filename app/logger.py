"""Configura il logging dell'applicazione e centralizza i log degli eventi rilevanti.

Non ogni riga di codice logga qualcosa: solo gli eventi che servono a capire cosa succede
in produzione senza dover leggere il codice — creazione ed esito di un job, retry, blocchi
di sicurezza, autenticazione fallita, migrazioni del database. Un metodo per evento, così
chi chiama non decide di volta in volta livello e formato del messaggio: sono già scelti qui.
"""

import logging

from app.config import LOG_LEVEL

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


class AppLogger:
    """Un metodo per ciascun evento rilevante del servizio."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("app")

    def job_created(self, job_id: str, url: str) -> None:
        self._logger.info("Job %s creato per %s", job_id, url)

    def job_unreachable(self, job_id: str, url: str) -> None:
        self._logger.warning("Job %s: URL non raggiungibile (%s)", job_id, url)

    def job_done(self, job_id: str, filename: str) -> None:
        self._logger.info("Job %s completato (%s)", job_id, filename)

    def job_failed(self, job_id: str, error: str) -> None:
        self._logger.error("Job %s: errore durante la cattura (%s)", job_id, error)

    def job_not_found(self, job_id: str) -> None:
        self._logger.error("Job %s: non trovato, impossibile processarlo", job_id)

    def job_retried(self, job_id: str) -> None:
        self._logger.info("Job %s rimesso in coda per un nuovo tentativo", job_id)

    def ssrf_blocked(self, url: str) -> None:
        self._logger.warning("URL bloccato (protezione SSRF): %s", url)

    def redirect_blocked(self, url: str) -> None:
        self._logger.warning("Redirect bloccato durante la navigazione (protezione SSRF): %s", url)

    def auth_failed(self, path: str) -> None:
        self._logger.warning("Richiesta rifiutata: API key mancante o non valida (%s)", path)

    def browser_started(self) -> None:
        self._logger.info("Browser Chromium condiviso avviato")

    def browser_restarted(self) -> None:
        self._logger.warning("Browser Chromium condiviso non raggiungibile: ne avvio uno nuovo")


app_logger = AppLogger()
