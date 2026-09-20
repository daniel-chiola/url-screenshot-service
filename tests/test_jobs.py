"""Test per app/jobs.py."""

import pytest

from app import jobs

# Applica il marker "anyio" a tutte le funzioni async di questo file, così
# pytest sa che deve eseguirle come coroutine invece di ignorarle.
pytestmark = pytest.mark.anyio


# --- create_job / get_job / list_jobs: nessun mock, sono funzioni semplici ---
#
# I job sono persistiti su SQLite (app/db.py): get_job/list_jobs non restituiscono
# più lo stesso oggetto Python passato a create_job, ma una nuova istanza letta dal
# DB. Per questo confrontiamo i valori (==) invece dell'identità dell'oggetto (is).


async def test_create_job_valori_di_default():
    """Un job appena creato ha i valori di default attesi e stato 'pending'."""
    job = await jobs.create_job("https://example.com")

    assert job.url == "https://example.com"
    assert job.status == "pending"
    assert job.width == 1280
    assert job.height == 800
    assert job.full_page is False
    assert job.filename is None


async def test_create_job_registra_il_job_nella_coda():
    """create_job salva il job nella coda: get_job lo ritrova subito dopo."""
    job = await jobs.create_job("https://example.com")

    assert await jobs.get_job(job.id) == job


async def test_get_job_con_id_inesistente_torna_none():
    """get_job con un id sconosciuto torna None, non solleva un errore."""
    assert await jobs.get_job("id-che-non-esiste") is None


async def test_list_jobs_mostra_il_piu_recente_per_primo():
    """list_jobs ordina i job dal più recente al più vecchio."""
    first = await jobs.create_job("https://uno.com")
    second = await jobs.create_job("https://due.com")

    result = await jobs.list_jobs()

    assert result[0].id == second.id
    assert result[1].id == first.id


async def test_list_jobs_rispetta_il_limite():
    """list_jobs non restituisce mai più job del limite richiesto."""
    for i in range(5):
        await jobs.create_job(f"https://esempio{i}.com")

    result = await jobs.list_jobs(limit=2)

    assert len(result) == 2


# --- count_jobs / avg_seconds_to_completion ---


async def test_count_jobs_senza_filtro_conta_tutti():
    """count_jobs senza argomenti conta tutti i job, di qualsiasi stato."""
    await jobs.create_job("https://uno.com")
    await jobs.create_job("https://due.com")

    assert await jobs.count_jobs() == 2


async def test_count_jobs_filtra_per_stato():
    """count_jobs(status=...) conta solo i job in quello stato."""
    await jobs.create_job("https://uno.com")  # resta "pending"

    assert await jobs.count_jobs(status="pending") == 1
    assert await jobs.count_jobs(status="done") == 0


async def test_avg_seconds_to_completion_none_senza_job_completati():
    """avg_seconds_to_completion torna None se nessun job è ancora in done/error."""
    await jobs.create_job("https://uno.com")  # resta "pending", non conta

    assert await jobs.avg_seconds_to_completion() is None


async def test_avg_seconds_to_completion_include_sia_done_che_error(monkeypatch):
    """avg_seconds_to_completion misura il tempo medio tra creazione e completamento, done ed error insieme."""
    async def fake_is_reachable_ok(url):
        return True

    async def fake_capture_screenshot(url, output_path, **kwargs):
        pass

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable_ok)
    monkeypatch.setattr(jobs, "capture_screenshot", fake_capture_screenshot)
    job_done = await jobs.create_job("https://example.com")
    await jobs.process_job(job_done.id)  # → "done"

    async def fake_is_reachable_ko(url):
        return False

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable_ko)
    job_error = await jobs.create_job("https://esempio-morto.com")
    await jobs.process_job(job_error.id)  # → "error"

    avg = await jobs.avg_seconds_to_completion()

    assert avg is not None
    assert avg >= 0


# --- process_job: qui servono i mock, per non chiamare rete/browser veri ---
#
# jobs.py fa `from app.utils import is_reachable` e `from app.screenshot import
# capture_screenshot`: questo copia un riferimento a quelle funzioni dentro il
# namespace di app.jobs. Per sostituirle nei test dobbiamo quindi "patchare"
# jobs.is_reachable / jobs.capture_screenshot (dove vengono USATE), non
# app.utils.is_reachable (dove sono DEFINITE) — altrimenti jobs.py continuerebbe
# a usare la versione vera, perché il suo riferimento non cambia.
#
# Nota: dopo process_job() il job va ri-letto con get_job(), non basta controllare
# l'oggetto `job` originale — non è più la stessa istanza mutata in place come con
# il vecchio dizionario in-memory, ma una copia letta dal DB al momento della create.


async def test_process_job_id_inesistente_non_solleva_errore():
    """process_job su un id inesistente (es. job cancellato nel frattempo) non fallisce."""
    await jobs.process_job("id-che-non-esiste")  # non deve sollevare eccezioni


async def test_process_job_url_non_raggiungibile(monkeypatch):
    """Se l'URL non è raggiungibile, il job va in 'error' senza tentare la cattura."""
    async def fake_is_reachable(url):
        return False

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable)

    job = await jobs.create_job("https://esempio-morto.com")
    await jobs.process_job(job.id)

    updated = await jobs.get_job(job.id)
    assert updated.status == "error"
    assert updated.error == "URL non raggiungibile"


async def test_process_job_cattura_riuscita(monkeypatch):
    """Se la cattura va a buon fine, il job passa a 'done' con il filename impostato."""
    async def fake_is_reachable(url):
        return True

    async def fake_capture_screenshot(url, output_path, **kwargs):
        pass  # finge che la cattura sia andata a buon fine, senza aprire un browser vero

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable)
    monkeypatch.setattr(jobs, "capture_screenshot", fake_capture_screenshot)

    job = await jobs.create_job("https://example.com")
    await jobs.process_job(job.id)

    updated = await jobs.get_job(job.id)
    assert updated.status == "done"
    assert updated.filename == "screenshot_example_com.png"


async def test_process_job_cattura_fallita(monkeypatch):
    """Se capture_screenshot solleva un'eccezione, il job va in 'error' con il messaggio."""
    async def fake_is_reachable(url):
        return True

    async def fake_capture_screenshot(url, output_path, **kwargs):
        raise RuntimeError("Playwright è esploso")

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable)
    monkeypatch.setattr(jobs, "capture_screenshot", fake_capture_screenshot)

    job = await jobs.create_job("https://example.com")
    await jobs.process_job(job.id)

    updated = await jobs.get_job(job.id)
    assert updated.status == "error"
    assert updated.error == "Playwright è esploso"


# --- retry_job ---


async def test_retry_job_rimette_in_coda_un_job_fallito(monkeypatch):
    """retry_job riporta un job da 'error' a 'pending', ripulendo errore e filename."""
    async def fake_is_reachable(url):
        return False

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable)

    job = await jobs.create_job("https://esempio-morto.com")
    await jobs.process_job(job.id)

    retried = await jobs.retry_job(job.id)

    assert retried.status == "pending"
    assert retried.error is None
    assert retried.filename is None


async def test_retry_job_rifiuta_un_job_non_in_errore():
    """retry_job su un job che non è in stato 'error' (es. 'pending') torna None."""
    job = await jobs.create_job("https://example.com")

    assert await jobs.retry_job(job.id) is None


async def test_retry_job_con_id_inesistente_torna_none():
    """retry_job con un id sconosciuto torna None, non solleva un errore."""
    assert await jobs.retry_job("id-che-non-esiste") is None
