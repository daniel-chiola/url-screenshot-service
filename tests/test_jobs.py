"""Test per app/jobs.py."""

import pytest

from app import jobs

# Applica il marker "anyio" a tutte le funzioni async di questo file, così
# pytest sa che deve eseguirle come coroutine invece di ignorarle.
pytestmark = pytest.mark.anyio


# --- create_job / get_job / list_jobs: nessun mock, sono funzioni semplici ---


def test_create_job_valori_di_default():
    job = jobs.create_job("https://example.com")

    assert job.url == "https://example.com"
    assert job.status == "pending"
    assert job.width == 1280
    assert job.height == 800
    assert job.full_page is False
    assert job.filename is None


def test_create_job_registra_il_job_nella_coda():
    job = jobs.create_job("https://example.com")

    assert jobs.get_job(job.id) is job


def test_get_job_con_id_inesistente_torna_none():
    assert jobs.get_job("id-che-non-esiste") is None


def test_list_jobs_mostra_il_piu_recente_per_primo():
    primo = jobs.create_job("https://uno.com")
    secondo = jobs.create_job("https://due.com")

    risultato = jobs.list_jobs()

    assert risultato[0].id == secondo.id
    assert risultato[1].id == primo.id


def test_list_jobs_rispetta_il_limite():
    for i in range(5):
        jobs.create_job(f"https://esempio{i}.com")

    risultato = jobs.list_jobs(limit=2)

    assert len(risultato) == 2


# --- process_job: qui servono i mock, per non chiamare rete/browser veri ---
#
# jobs.py fa `from app.utils import is_reachable` e `from app.screenshot import
# capture_screenshot`: questo copia un riferimento a quelle funzioni dentro il
# namespace di app.jobs. Per sostituirle nei test dobbiamo quindi "patchare"
# jobs.is_reachable / jobs.capture_screenshot (dove vengono USATE), non
# app.utils.is_reachable (dove sono DEFINITE) — altrimenti jobs.py continuerebbe
# a usare la versione vera, perché il suo riferimento non cambia.


async def test_process_job_url_non_raggiungibile(monkeypatch):
    async def fake_is_reachable(url):
        return False

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable)

    job = jobs.create_job("https://esempio-morto.com")
    await jobs.process_job(job.id)

    assert job.status == "error"
    assert job.error == "URL non raggiungibile"


async def test_process_job_cattura_riuscita(monkeypatch):
    async def fake_is_reachable(url):
        return True

    async def fake_capture_screenshot(url, output_path, **kwargs):
        pass  # finge che la cattura sia andata a buon fine, senza aprire un browser vero

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable)
    monkeypatch.setattr(jobs, "capture_screenshot", fake_capture_screenshot)

    job = jobs.create_job("https://example.com")
    await jobs.process_job(job.id)

    assert job.status == "done"
    assert job.filename == "screenshot_example_com.png"


async def test_process_job_cattura_fallita(monkeypatch):
    async def fake_is_reachable(url):
        return True

    async def fake_capture_screenshot(url, output_path, **kwargs):
        raise RuntimeError("Playwright è esploso")

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable)
    monkeypatch.setattr(jobs, "capture_screenshot", fake_capture_screenshot)

    job = jobs.create_job("https://example.com")
    await jobs.process_job(job.id)

    assert job.status == "error"
    assert job.error == "Playwright è esploso"
