# url-screenshot-service

Servizio containerizzato che riceve un URL via API REST, genera uno screenshot della pagina con Chromium headless (Playwright) e lo salva su file.

## Architettura

- **FastAPI**: espone `POST /screenshot` che accetta `{"url": "..."}` e restituisce il percorso del file salvato.
- **Playwright (Chromium headless)**: apre la pagina e cattura lo screenshot.
- **Volume Docker**: gli screenshot vengono salvati in `./screenshots` sull'host, montata nel container.

## Setup

```bash
docker compose up --build
```

Il servizio sarà disponibile su `http://localhost:8000`.

## Utilizzo

```bash
curl -X POST http://localhost:8000/screenshot \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.google.com"}'
```

Lo screenshot verrà salvato in `screenshots/` con un nome derivato dall'URL (es. `screenshot_google_com.png`).

## TODO

- [ ] Implementare `url_to_filename` in [app/utils.py](app/utils.py)
- [ ] Implementare `capture_screenshot` in [app/screenshot.py](app/screenshot.py)
- [ ] Implementare l'endpoint `/screenshot` in [app/main.py](app/main.py)
- [ ] Logging e gestione errori (URL non raggiungibili, timeout, ecc.)
- [ ] Retry per URL non accessibili (extra)
- [ ] UI web minimale (extra)
