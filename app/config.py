"""Configurazione del servizio, letta da variabili d'ambiente."""

import os

SCREENSHOTS_DIR = os.getenv("SCREENSHOTS_DIR", "/app/screenshots")

# File SQLite in cui viene persistita la coda dei job: sopravvive ai riavvii del container.
DB_PATH = os.getenv("DB_PATH", "/app/data/jobs.db")

# Numero massimo di catture Playwright eseguite in parallelo (protegge la memoria del container)
MAX_CONCURRENT_CAPTURES = int(os.getenv("MAX_CONCURRENT_CAPTURES", "2"))

# Limite di richieste POST /screenshot per IP (sintassi slowapi, es. "5/minute")
RATE_LIMIT = os.getenv("RATE_LIMIT", "5/minute")

# Se impostata, protegge gli endpoint funzionali con un header "X-API-Key".
# Se lasciata vuota (default), l'autenticazione è disattivata: comodo per
# provare il servizio in locale, ma va impostata per qualsiasi uso reale.
API_KEY = os.getenv("API_KEY", "")
