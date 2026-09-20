"""Test app/main.py."""

import pytest
from fastapi.testclient import TestClient

from app import jobs, main
from app.main import app

# Applica il marker "anyio" a tutte le funzioni async di questo file (TestClient
# resta comunque sincrono da chiamare, anche dentro un test async: fa da ponte
# lui stesso verso l'app asincrona, non serve mai "await" sulle sue chiamate).
pytestmark = pytest.mark.anyio

client = TestClient(app)

def test_health_check():
    """GET /health torna 200 OK."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_get_screenshot_not_found():
    """GET /screenshot/{id} con id non esistente torna 404 Not Found."""
    response = client.get("/screenshot/nonexistent-id")
    assert response.status_code == 404

async def test_get_screenshot_found():
    """GET /screenshot/{id} con id esistente torna 200 OK con i dettagli del job."""
    job = await jobs.create_job("https://www.example.com")

    response = client.get(f"/screenshot/{job.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job.id
    assert data["url"] == job.url
    assert data["status"] == job.status

async def test_get_jobs_list():
    """GET /jobs torna 200 OK con la lista dei job, più recente per primo."""
    job1 = await jobs.create_job("https://www.example.com")
    job2 = await jobs.create_job("https://www.example.org")

    response = client.get("/jobs")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["id"] == job2.id
    assert data[1]["id"] == job1.id


def test_screenshot_rate_limit(monkeypatch):
    """Oltre il limite di richieste per IP, POST /screenshot torna 429."""
    async def fake_is_reachable(url):
        return True

    async def fake_capture_screenshot(url, output_path, **kwargs):
        pass

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable)
    monkeypatch.setattr(jobs, "capture_screenshot", fake_capture_screenshot)

    for _ in range(5):
        response = client.post("/screenshot", json={"url": "https://www.example.com"})
        assert response.status_code == 202

    response = client.post("/screenshot", json={"url": "https://www.example.com"})
    assert response.status_code == 429  # Too Many Requests

def test_screenshot_missing_url():
    """POST /screenshot senza url torna 422 Unprocessable Entity."""
    response = client.post("/screenshot", json={})
    assert response.status_code == 422

def test_screenshot_invalid_url():
    """POST /screenshot con url non valido torna 422 Unprocessable Entity."""
    response = client.post("/screenshot", json={"url": "invalid-url"})
    assert response.status_code == 422

def test_screenshot_private_url():
    """POST /screenshot con url privato torna 403 Forbidden."""
    response = client.post("/screenshot", json={"url": "http://localhost"})
    assert response.status_code == 403

def test_screenshot(monkeypatch):
    """POST /screenshot con URL valido crea un job e torna 202 con id e stato 'pending'."""
    async def fake_is_reachable(url):
        return True

    async def fake_capture_screenshot(url, output_path, **kwargs):
        pass

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable)
    monkeypatch.setattr(jobs, "capture_screenshot", fake_capture_screenshot)

    response = client.post("/screenshot", json={"url": "https://www.example.com"})

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    assert "id" in data


def test_screenshot_richiede_api_key_se_configurata(monkeypatch):
    """Con API_KEY configurata, POST /screenshot senza header X-API-Key torna 401."""
    monkeypatch.setattr(main, "API_KEY", "segreto-di-test")

    response = client.post("/screenshot", json={"url": "https://www.example.com"})

    assert response.status_code == 401

def test_screenshot_rifiuta_api_key_sbagliata(monkeypatch):
    """Con API_KEY configurata, un X-API-Key sbagliato torna 401."""
    monkeypatch.setattr(main, "API_KEY", "segreto-di-test")

    response = client.post(
        "/screenshot",
        json={"url": "https://www.example.com"},
        headers={"X-API-Key": "sbagliato"},
    )

    assert response.status_code == 401

def test_screenshot_accetta_api_key_corretta(monkeypatch):
    """Con API_KEY configurata, il X-API-Key corretto lascia passare la richiesta."""
    monkeypatch.setattr(main, "API_KEY", "segreto-di-test")

    async def fake_is_reachable(url):
        return True

    async def fake_capture_screenshot(url, output_path, **kwargs):
        pass

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable)
    monkeypatch.setattr(jobs, "capture_screenshot", fake_capture_screenshot)

    response = client.post(
        "/screenshot",
        json={"url": "https://www.example.com"},
        headers={"X-API-Key": "segreto-di-test"},
    )

    assert response.status_code == 202

def test_health_pubblico_anche_con_api_key_configurata(monkeypatch):
    """GET /health resta pubblico anche con API_KEY configurata."""
    monkeypatch.setattr(main, "API_KEY", "segreto-di-test")

    response = client.get("/health")

    assert response.status_code == 200


# --- POST /screenshot/{id}/retry ---


def test_retry_screenshot_job_inesistente():
    """POST /screenshot/{id}/retry con id sconosciuto torna 404."""
    response = client.post("/screenshot/id-che-non-esiste/retry")
    assert response.status_code == 404

async def test_retry_screenshot_job_non_in_errore():
    """POST /screenshot/{id}/retry su un job non in stato 'error' torna 404."""
    job = await jobs.create_job("https://www.example.com")  # resta 'pending'

    response = client.post(f"/screenshot/{job.id}/retry")

    assert response.status_code == 404

async def test_retry_screenshot_rimette_in_coda_un_job_fallito(monkeypatch):
    """POST /screenshot/{id}/retry su un job fallito lo rimette in coda e lo riprocessa."""
    async def fake_is_reachable_ko(url):
        return False

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable_ko)

    job = await jobs.create_job("https://esempio-morto.com")
    await jobs.process_job(job.id)  # lo porta in stato 'error'

    async def fake_is_reachable_ok(url):
        return True

    async def fake_capture_screenshot(url, output_path, **kwargs):
        pass

    monkeypatch.setattr(jobs, "is_reachable", fake_is_reachable_ok)
    monkeypatch.setattr(jobs, "capture_screenshot", fake_capture_screenshot)

    response = client.post(f"/screenshot/{job.id}/retry")

    assert response.status_code == 202
    data = response.json()
    assert data["id"] == job.id

    updated = await jobs.get_job(job.id)
    assert updated.status == "done"
    assert updated.error is None
