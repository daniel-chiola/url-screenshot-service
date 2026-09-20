"""Test per app/screenshot.py.

Solo _make_route_guard: è logica pura (nessuna chiamata a Playwright/Chromium), quindi
testabile senza un browser vero. capture_screenshot() invece apre davvero Chromium e resta
fuori da questa suite (vedi la nota sulla coverage nel README).
"""

import pytest

from app.screenshot import _make_route_guard

pytestmark = pytest.mark.anyio


class FakeRequest:
    """Finge una playwright.async_api.Request: basta url e resource_type."""

    def __init__(self, url: str, resource_type: str) -> None:
        self.url = url
        self.resource_type = resource_type


class FakeRoute:
    """Finge una playwright.async_api.Route: registra se è stata abortita o continuata."""

    def __init__(self, request: FakeRequest) -> None:
        self.request = request
        self.aborted = False
        self.continued = False

    async def abort(self) -> None:
        self.aborted = True

    async def continue_(self) -> None:
        self.continued = True


async def test_guard_blocca_un_documento_verso_un_indirizzo_non_sicuro(monkeypatch):
    """Il guard blocca la navigazione (resource_type 'document') se l'URL non passa il controllo SSRF."""
    async def fake_is_safe_url(url):
        return False

    monkeypatch.setattr("app.screenshot.is_safe_url", fake_is_safe_url)
    guard = _make_route_guard(block_ads=True)
    route = FakeRoute(FakeRequest("http://169.254.169.254/", "document"))

    await guard(route)

    assert route.aborted is True
    assert route.continued is False


async def test_guard_lascia_passare_un_documento_verso_un_indirizzo_sicuro(monkeypatch):
    """Il guard lascia proseguire la navigazione se l'URL passa il controllo SSRF."""
    async def fake_is_safe_url(url):
        return True

    monkeypatch.setattr("app.screenshot.is_safe_url", fake_is_safe_url)
    guard = _make_route_guard(block_ads=True)
    route = FakeRoute(FakeRequest("https://example.com/", "document"))

    await guard(route)

    assert route.continued is True
    assert route.aborted is False


async def test_guard_blocca_le_richieste_pubblicitarie_se_block_ads_attivo(monkeypatch):
    """Con block_ads=True, le richieste verso i domini pubblicitari noti vengono bloccate."""
    async def fake_is_safe_url(url):
        return True

    monkeypatch.setattr("app.screenshot.is_safe_url", fake_is_safe_url)
    guard = _make_route_guard(block_ads=True)
    route = FakeRoute(FakeRequest("https://doubleclick.net/pixel.gif", "image"))

    await guard(route)

    assert route.aborted is True


async def test_guard_lascia_passare_le_richieste_pubblicitarie_se_block_ads_disattivo(monkeypatch):
    """Con block_ads=False, le richieste verso i domini pubblicitari passano."""
    guard = _make_route_guard(block_ads=False)
    route = FakeRoute(FakeRequest("https://doubleclick.net/pixel.gif", "image"))

    await guard(route)

    assert route.continued is True


async def test_guard_lascia_passare_una_risorsa_normale(monkeypatch):
    """Una risorsa non-documento e non pubblicitaria (es. un'immagine della pagina) passa sempre."""
    guard = _make_route_guard(block_ads=True)
    route = FakeRoute(FakeRequest("https://example.com/logo.png", "image"))

    await guard(route)

    assert route.continued is True
