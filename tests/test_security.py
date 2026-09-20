"""Test per app/security.py."""

import socket

import pytest

from app import security

# Applica il marker "anyio" a tutte le funzioni async di questo file, così
# pytest sa che deve eseguirle come coroutine invece di ignorarle.
pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("ip, expected", [
    ("192.168.1.1", True),             # privato
    ("10.0.0.1", True),                # privato
    ("172.16.0.1", True),              # privato
    ("8.8.8.8", False),                # pubblico
    ("127.0.0.1", True),               # loopback
    ("169.254.0.1", True),             # link-local
    ("240.0.0.1", True),               # reserved
    ("224.0.0.1", True),               # multicast
    ("0.0.0.0", True),                 # unspecified
    ("not.an.ip", True),               # non valido
    ("::1", True),                     # IPv6 loopback
    ("fc00::1", True),                 # IPv6 privato
    ("2001:4860:4860::8888", False),   # IPv6 pubblico
])
def test_is_unsafe_ip(ip, expected):
    """_is_unsafe_ip riconosce correttamente IP privati/riservati/non validi, sia IPv4 che IPv6."""
    assert security._is_unsafe_ip(ip) is expected


async def test_is_safe_url_host_pubblico(monkeypatch):
    """Un host che risolve solo a IP pubblici è considerato sicuro."""
    async def fake_to_thread(func, *args):
        return [(2, 1, 6, "", ("8.8.8.8", 9))]

    monkeypatch.setattr(security.asyncio, "to_thread", fake_to_thread)

    assert await security.is_safe_url("https://example.com") is True


async def test_is_safe_url_ip_privato(monkeypatch):
    """Un host che risolve a un IP privato viene bloccato."""
    async def fake_to_thread(func, *args):
        return [(2, 1, 6, "", ("192.168.1.1", 9))]

    monkeypatch.setattr(security.asyncio, "to_thread", fake_to_thread)

    assert await security.is_safe_url("https://example.com") is False


async def test_is_safe_url_piu_ip_uno_privato(monkeypatch):
    """Se anche solo uno degli IP risolti è privato, l'host viene bloccato."""
    async def fake_to_thread(func, *args):
        return [
            (2, 1, 6, "", ("192.168.1.1", 9)),
            (2, 1, 6, "", ("8.8.8.8", 9)),
        ]

    monkeypatch.setattr(security.asyncio, "to_thread", fake_to_thread)

    assert await security.is_safe_url("https://example.com") is False


async def test_is_safe_url_senza_host():
    """Un URL senza host viene bloccato subito, senza bisogno di risolvere nulla."""
    assert await security.is_safe_url("") is False


async def test_is_safe_url_dns_fallita(monkeypatch):
    """Se la risoluzione DNS fallisce, l'host viene considerato non sicuro."""
    async def fake_to_thread(func, *args):
        raise socket.gaierror("simulato")

    monkeypatch.setattr(security.asyncio, "to_thread", fake_to_thread)

    assert await security.is_safe_url("https://esempio-morto.test") is False
