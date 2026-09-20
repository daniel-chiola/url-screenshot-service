"""Impedisce al servizio di visitare indirizzi che non dovrebbe raggiungere.

Il servizio va a caricare qualsiasi URL gli venga passato: senza controlli, qualcuno
potrebbe farlo puntare a `localhost`, a un IP della rete interna del container, o a
indirizzi riservati usati dai provider cloud per esporre dati sensibili della macchina.
Questo modulo controlla, prima di procedere, che l'URL non porti a uno di questi posti.
"""

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
    """True se l'host dell'URL punta solo a indirizzi IP pubblici.

    Risolve il nome host in uno o più IP (un host può risolvere a più indirizzi) e li
    controlla tutti: se anche uno solo è privato, interno, o riservato, la funzione
    ritorna False. Questo copre anche l'indirizzo 169.254.169.254, usato da AWS/GCP/Azure
    per esporre metadati (a volte credenziali) della macchina che esegue il container.
    """
    hostname = urlparse(url).hostname
    if not hostname:
        return False
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror:
        return False
    return not any(_is_unsafe_ip(info[4][0]) for info in infos)
