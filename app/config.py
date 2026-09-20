"""Configurazione del servizio, letta da variabili d'ambiente."""

import os

SCREENSHOTS_DIR = os.getenv("SCREENSHOTS_DIR", "/app/screenshots")

# Numero massimo di catture Playwright eseguite in parallelo (protegge la memoria del container)
MAX_CONCURRENT_CAPTURES = int(os.getenv("MAX_CONCURRENT_CAPTURES", "2"))

# Limite di richieste POST /screenshot per IP (sintassi slowapi, es. "5/minute")
RATE_LIMIT = os.getenv("RATE_LIMIT", "5/minute")
