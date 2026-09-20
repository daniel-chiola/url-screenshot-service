# url-screenshot-service

Servizio containerizzato che riceve un URL via API REST, genera uno screenshot della pagina con Chromium headless (Playwright) e lo salva su file.

## Architettura

Il servizio è **asincrono**: `POST /screenshot` non aspetta che la cattura sia completata. Accoda un job in background e risponde subito con un id; lo stato si interroga poi con `GET /screenshot/{id}` (o si osserva l'intera coda con `GET /jobs`).

```
Browser (UI su "/")  ──┐
                        │  POST /screenshot {"url": "..."}
Client (curl / Swagger UI) ──┤
                        ▼
                FastAPI (app/main.py)
                        │  valida l'URL, rate limit per IP (slowapi)
                        │  crea il job (app/jobs.py) → 202 {"id", "status": "pending"}
                        │  schedula process_job() in BackgroundTasks
                        ▼
                app/jobs.py — process_job()
                        │  verifica raggiungibilità via HTTP (app/utils.py)
                        │    └─ non raggiungibile → job in stato "error"
                        │  deriva il nome file (app/utils.py)
                        │  semaforo: max N catture Playwright in parallelo
                        ▼
        Playwright / Chromium headless (app/screenshot.py)
                        │  apre la pagina, cattura lo screenshot
                        │  (retry con backoff esponenziale sui timeout)
                        ▼
        Filesystem — ./screenshots (volume Docker) — job → stato "done"
                        │
                        ▼  servito come statico su GET /screenshots/<file>
     Browser (polling su GET /screenshot/{id} e GET /jobs, mostra risultato e coda)
```

Componenti:

- **FastAPI** ([app/main.py](app/main.py)): espone `POST /screenshot` (crea un job e torna `202` con `{id, status}`), `GET /screenshot/{id}` (stato di un job), `GET /jobs` (coda completa) e `GET /health`. Il rate limit (`slowapi`) protegge `POST /screenshot` da richieste eccessive per IP.
- **Coda dei job** ([app/jobs.py](app/jobs.py)): job store in-memory (nessun DB/broker esterno). `process_job()` orchestra verifica di raggiungibilità, derivazione nome file e cattura, aggiornando lo stato del job (`pending` → `processing` → `done`/`error`). Un `asyncio.Semaphore` limita quante catture Playwright girano in parallelo, indipendentemente dal rate limit sulle richieste in ingresso.
- **Playwright (Chromium headless)** ([app/screenshot.py](app/screenshot.py)): apre la pagina e cattura lo screenshot, con retry automatico (`tenacity`, backoff esponenziale, max 3 tentativi) sui timeout di navigazione.
- **app/utils.py**: deriva un nome file sicuro dall'URL (es. `https://google.com` → `screenshot_google_com.png`) e verifica la raggiungibilità dell'URL via HTTP (`is_reachable`) prima di avviare il browser.
- **app/config.py**: configurazione centralizzata (directory di output, limite di concorrenza, rate limit — tutti letti da env var).
- **UI web minimale** ([app/static/index.html](app/static/index.html)): pagina HTML/JS vanilla servita su `GET /`. Form per inviare un URL con le opzioni di cattura (polling automatico sul job fino al risultato) e tabella che mostra l'intera coda in tempo reale.
- **Opzioni di cattura personalizzabili**: `width`/`height` (viewport), `full_page` (pagina intera vs solo viewport), `dark_mode` (`prefers-color-scheme: dark`), `block_ads` (blocca via `page.route()` le richieste verso i principali network pubblicitari/di tracking). Configurabili sia via API (`ScreenshotRequest`) sia dalla UI.
- **Volume Docker**: gli screenshot vengono salvati in `./screenshots` sull'host, montata nel container, così restano accessibili anche dopo lo stop del container. La stessa cartella è servita come file statici su `GET /screenshots/<filename>`.

### Scelte tecniche

- **Playwright invece di Selenium**: API più moderna, gestione automatica dei binari del browser, supporto nativo async.
- **`BackgroundTasks` invece di un broker esterno (Kafka/Redis)**: l'obiettivo era non far attendere il client durante la cattura, non costruire un sistema a eventi distribuito. `BackgroundTasks` risolve lo stesso problema restando nello stesso processo, senza infrastruttura aggiuntiva da configurare, testare e far girare in Docker — coerente con la scala di questo servizio (un solo worker, nessun bisogno di scalare orizzontalmente i consumer).
- **Job store in-memory invece di Redis/DB**: per un servizio a singolo processo è sufficiente; il costo è che lo stato dei job si perde a un riavvio, accettabile per questo caso d'uso.
- **Rate limit (`slowapi`) + semaforo di concorrenza**: sono due protezioni distinte e complementari. Il rate limit impedisce che un client spammi richieste (per IP, configurabile). Il semaforo limita quante istanze di Chromium girano contemporaneamente, indipendentemente da quante richieste sono arrivate: protegge la memoria del container anche da un singolo client che manda molte richieste legittime in sequenza.
- **Immagine base `mcr.microsoft.com/playwright/python`**: include già Chromium e tutte le dipendenze di sistema necessarie per l'headless, evitando di gestirle a mano nel Dockerfile.
- **uv** per la gestione delle dipendenze Python (locale e nel Dockerfile), al posto di pip/requirements.txt: risoluzione e installazione più veloci, lock file (`uv.lock`) per build riproducibili.
- **Pre-check HTTP invece di ping ICMP**: un ping ICMP è spesso bloccato da firewall/provider cloud anche su siti perfettamente raggiungibili via HTTP, e richiede permessi elevati (socket raw) che il container non ha. Una richiesta `HEAD`/`GET` con timeout breve è più affidabile e coerente con ciò che Playwright farà comunque.
- **`tenacity` per il retry**: gestisce backoff esponenziale e condizioni di stop in modo testato, evitando di reimplementare a mano una logica facile da sbagliare (es. mancanza di jitter). Il retry è mirato solo ai timeout di Playwright, non agli URL già scartati dal pre-check.

## Struttura del progetto

```
.
├── app/
│   ├── main.py           # FastAPI app, endpoint, rate limit ed export file statici
│   ├── jobs.py             # Coda in-memory dei job, semaforo di concorrenza
│   ├── screenshot.py      # Logica di cattura screenshot (Playwright)
│   ├── utils.py            # Derivazione nome file da URL, check raggiungibilità
│   ├── config.py           # Configurazione (directory output, rate limit, ecc.)
│   ├── schemas.py          # Modelli Pydantic (request/response)
│   └── static/
│       └── index.html      # UI web minimale
├── screenshots/             # Output degli screenshot (montata come volume)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml           # Dipendenze del progetto (gestite con uv)
└── uv.lock
```

## Prerequisiti

- Docker e Docker Compose (per l'esecuzione containerizzata)
- [uv](https://docs.astral.sh/uv/) (solo per lo sviluppo locale, senza Docker)

## Setup ed esecuzione

### Con Docker (consigliato)

Build dell'immagine e avvio in background (`-d` = detached, il terminale torna libero):

```bash
docker compose up -d --build
```

Il servizio sarà disponibile su `http://localhost:8000`. Gli screenshot generati vengono salvati nella cartella `./screenshots` sull'host.

Altri comandi utili:

```bash
# Vedere i log in tempo reale (utile per debug/errori)
docker compose logs -f

# Verificare che il container sia in esecuzione
docker compose ps

# Fermare il servizio
docker compose down

# Riavviare dopo una modifica al codice
docker compose up -d --build
```

Se `docker compose up -d --build` fallisce, controlla che Docker Desktop/OrbStack sia avviato.

### Sviluppo locale (senza Docker, con uv)

```bash
# 1. Installa le dipendenze Python nel venv del progetto (.venv/)
uv sync

# 2. Installa il browser Chromium richiesto da Playwright
uv run playwright install chromium --with-deps

# 3. Avvia il server con reload automatico (SCREENSHOTS_DIR: vedi nota sotto)
SCREENSHOTS_DIR=./screenshots uv run uvicorn app.main:app --reload
```

Il servizio sarà disponibile su `http://localhost:8000`.

> Il default di `SCREENSHOTS_DIR` (`/app/screenshots`) è pensato per il filesystem del container. In locale va sovrascritto con una directory esistente, es. `./screenshots` (vedi tabella [Configurazione](#configurazione)).

## Utilizzo e test

Una volta che il servizio è in esecuzione (`docker compose up -d --build`, oppure in locale con `uv`), puoi verificarlo in tre modi.

### 1. UI web (il modo più rapido)

Apri **`http://localhost:8000`** nel browser: form per inviare un URL (la pagina fa polling automatico e mostra lo screenshot appena pronto) e, sotto, una tabella con l'intera coda dei job in tempo reale.

### 2. Documentazione interattiva (Swagger UI)

Apri **`http://localhost:8000/docs`**: interfaccia auto-generata da FastAPI per esplorare e testare tutti gli endpoint (utile anche per vedere schema di request/response).

### 3. Da riga di comando (curl)

Health check — verifica rapida che il servizio sia su:

```bash
curl http://localhost:8000/health
# → {"status":"ok"}
```

Accodare una cattura (risposta immediata, `202`):

```bash
curl -X POST http://localhost:8000/screenshot \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.google.com"}'
# → {"id":"3f2...","status":"pending"}
```

Con opzioni personalizzate (tutte facoltative, i default sono quelli mostrati):

```bash
curl -X POST http://localhost:8000/screenshot \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.google.com",
    "width": 1280,
    "height": 800,
    "full_page": false,
    "dark_mode": false,
    "block_ads": true
  }'
```

Interrogare lo stato del job (con l'id restituito sopra):

```bash
curl http://localhost:8000/screenshot/3f2...
# → {"id":"3f2...","url":"https://www.google.com/","status":"done","filename":"screenshot_www.google.com.png","error":null,"created_at":"..."}
```

Vedere l'intera coda:

```bash
curl http://localhost:8000/jobs
```

Recuperare l'immagine generata via HTTP (filename dallo stato del job):

```bash
curl -o out.png http://localhost:8000/screenshots/screenshot_www.google.com.png
```

### Verificare il file salvato su disco

Con Docker, il volume espone la cartella sull'host, quindi:

```bash
ls -la screenshots/
```

deve mostrare il file appena generato.

## Configurazione

| Variabile                | Default              | Descrizione                                  |
|---------------------------|----------------------|-----------------------------------------------|
| `SCREENSHOTS_DIR`         | `/app/screenshots`   | Directory in cui vengono salvati gli screenshot |
| `MAX_CONCURRENT_CAPTURES` | `2`                  | Numero massimo di catture Playwright in parallelo |
| `RATE_LIMIT`              | `5/minute`           | Limite di richieste `POST /screenshot` per IP (sintassi `slowapi`) |

## TODO

- [x] Implementare `url_to_filename` in [app/utils.py](app/utils.py)
- [x] Implementare `capture_screenshot` in [app/screenshot.py](app/screenshot.py)
- [x] Implementare l'endpoint `/screenshot` in [app/main.py](app/main.py)
- [x] Logging e gestione errori (URL non raggiungibili, timeout, ecc.)
- [x] Retry per URL non accessibili (extra)
- [x] UI web minimale (extra)
