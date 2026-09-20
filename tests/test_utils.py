"""Test per app/utils.py."""

import pytest

from app import utils

# Applica il marker "anyio" a tutte le funzioni async di questo file, così
# pytest sa che deve eseguirle come coroutine invece di ignorarle.
pytestmark = pytest.mark.anyio


def test_url_to_filename():
    """url_to_filename deriva il nome file dall'host dell'URL, sostituendo i punti con underscore."""
    assert utils.url_to_filename("https://google.com") == "screenshot_google_com.png"
    assert utils.url_to_filename("http://example.org/path/to/page") == "screenshot_example_org.png"
    assert utils.url_to_filename("https://sub.domain.co.uk/") == "screenshot_sub_domain_co_uk.png"


async def test_is_reachable_url_raggiungibile(monkeypatch):
    """is_reachable torna True se il server risponde con uno status code sotto i 400."""
    class FakeResponse:
        status_code = 200

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def head(self, url):
            return FakeResponse()

    monkeypatch.setattr(utils.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient())

    result = await utils.is_reachable("https://example.com")

    assert result is True


async def test_is_reachable_fallback_su_get_se_head_non_supportato(monkeypatch):
    """Se il server risponde 405 a HEAD, is_reachable ritenta con GET."""
    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def head(self, url):
            return FakeResponse(405)

        async def get(self, url):
            return FakeResponse(200)

    monkeypatch.setattr(utils.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient())

    result = await utils.is_reachable("https://example.com")

    assert result is True


async def test_is_reachable_errore_di_rete(monkeypatch):
    """Se la richiesta fallisce (errore di rete), is_reachable ritorna False."""
    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def head(self, url):
            raise utils.httpx.RequestError("simulato")

    monkeypatch.setattr(utils.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient())

    result = await utils.is_reachable("https://esempio-morto.test")

    assert result is False