"""Test app/main.py."""

from fastapi.testclient import TestClient

from app import jobs
from app.main import app

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

def test_get_screenshot_found():
    """GET /screenshot/{id} con id esistente torna 200 OK con i dettagli del job."""
    job = jobs.create_job("https://www.example.com")

    response = client.get(f"/screenshot/{job.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job.id
    assert data["url"] == job.url
    assert data["status"] == job.status

def test_get_jobs_list():
    """GET /jobs torna 200 OK con la lista dei job, più recente per primo."""
    job1 = jobs.create_job("https://www.example.com")
    job2 = jobs.create_job("https://www.example.org")

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