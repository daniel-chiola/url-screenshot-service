"""Protezione SSRF: impedisce al servizio di raggiungere indirizzi IP privati o riservati."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


def _is_unsafe_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # non un IP valido: per prudenza, blocca
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


async def is_safe_url(url: str) -> bool:
    """False se l'host dell'URL risolve (anche solo parzialmente) a un IP privato/riservato/loopback.

    Copre anche l'endpoint di metadata cloud (169.254.169.254, in range link-local).
    """
    hostname = urlparse(url).hostname
    if not hostname:
        return False
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror:
        return False
    return not any(_is_unsafe_ip(info[4][0]) for info in infos)
