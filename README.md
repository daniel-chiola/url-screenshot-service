# url-screenshot-service

[![CI](https://github.com/daniel-chiola/url-screenshot-service/actions/workflows/ci.yml/badge.svg)](https://github.com/daniel-chiola/url-screenshot-service/actions/workflows/ci.yml)

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
                        │  blocca IP privati/riservati (app/security.py) → 403 se non sicuro
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
                        │  ri-verifica ogni navigazione/redirect (protezione SSRF)
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
- **app/security.py**: protezione SSRF (`is_safe_url`) — risolve l'host via DNS e blocca IP privati, loopback, link-local (incluso l'endpoint di metadata cloud `169.254.169.254`), riservati o multicast.
- **app/config.py**: configurazione centralizzata (directory di output, limite di concorrenza, rate limit — tutti letti da env var).
- **UI web minimale** ([app/static/index.html](app/static/index.html)): pagina HTML/JS vanilla servita su `GET /`. Form per inviare un URL con le opzioni di cattura (polling automatico sul job fino al risultato) e tabella che mostra l'intera coda in tempo reale.
- **Opzioni di cattura personalizzabili**: `width`/`height` (viewport), `full_page` (pagina intera vs solo viewport), `dark_mode` (`prefers-color-scheme: dark`), `block_ads` (blocca via `page.route()` le richieste verso i principali network pubblicitari/di tracking). Configurabili sia via API (`ScreenshotRequest`) sia dalla UI.
- **Volume Docker**: gli screenshot vengono salvati in `./screenshots` sull'host, montata nel container, così restano accessibili anche dopo lo stop del container. La stessa cartella è servita come file statici su `GET /screenshots/<filename>`.

### Sicurezza

Un servizio che va a fetchare URL arbitrari forniti dall'utente è per natura esposto a **SSRF** (Server-Side Request Forgery): senza controlli, potrebbe essere usato per raggiungere risorse interne alla rete del container (`localhost`, IP privati, endpoint di metadata cloud come `169.254.169.254`). Le difese implementate:

- **Validazione base del formato URL** ([app/schemas.py](app/schemas.py)): il campo `url` di `ScreenshotRequest` è tipizzato `pydantic.HttpUrl`, quindi FastAPI/Pydantic rifiutano automaticamente con `422` qualsiasi valore non sia un URL http/https ben formato, prima ancora che il codice applicativo (incluso il controllo SSRF sotto) venga eseguito.
- **Controllo all'ingresso** ([app/security.py](app/security.py), usato in [app/main.py](app/main.py)): prima di accodare qualunque job, l'host dell'URL viene risolto via DNS e ogni IP risultante viene verificato contro i range privati/loopback/link-local/riservati/multicast (modulo `ipaddress` della stdlib). Se anche un solo IP risolto è "non sicuro", la richiesta viene rifiutata con `403` — il job non viene nemmeno creato.
- **Controllo ad ogni navigazione/redirect** ([app/screenshot.py](app/screenshot.py)): il solo controllo iniziale non basta, perché un URL pubblico può reindirizzare a un indirizzo interno *dopo* il controllo (bypass classico). Playwright viene istruito (`page.route()`) a ri-validare l'host di **ogni** richiesta di navigazione (incluso ogni hop di redirect) prima di lasciarla proseguire, non solo dell'URL iniziale.
- **`is_reachable` senza follow-redirect** ([app/utils.py](app/utils.py)): il pre-check HTTP non segue più i redirect (`follow_redirects=False`) — un 3xx conta comunque come raggiungibile (`< 400`), quindi il risultato non cambia. Seguirli, però, permetterebbe di usare questo controllo per capire se un indirizzo interno risponde o no, prima ancora che scatti la protezione vera e propria in Playwright.
- **Autenticazione via API key** ([app/main.py](app/main.py)): se la variabile `API_KEY` è impostata, `POST /screenshot`, `GET /screenshot/{id}` e `GET /jobs` richiedono l'header `X-API-Key` con il valore corretto, altrimenti `401`. `GET /health` resta sempre pubblico (è pensato per load balancer/orchestratori, che non hanno credenziali). Di default `API_KEY` è vuota e l'autenticazione è disattivata, per poter provare il servizio subito senza configurazione — va impostata per qualsiasi esposizione pubblica reale.
- **Container non-root** ([Dockerfile](Dockerfile)): lo stage `runtime` esegue come `pwuser` (utente non privilegiato già presente nell'immagine Playwright), non come root — principio del minimo privilegio: se il servizio venisse compromesso, l'attaccante erediterebbe i permessi di un utente limitato, non di root. Vale anche per il processo Chromium lanciato da Playwright, non solo per il server web. L'interprete Python gestito da `uv` viene installato dentro `/app` (`UV_PYTHON_INSTALL_DIR`) invece che nella home di root, altrimenti `pwuser` non riuscirebbe nemmeno ad avviare l'app.

**Limite noto, dichiarato onestamente**: resta un'esposizione teorica a DNS rebinding (l'host risolve a un IP pubblico al momento del controllo, poi il DNS cambia risposta prima della connessione effettiva). Chiuderlo del tutto richiederebbe pinnare l'IP risolto e usarlo direttamente per la connessione TCP (bypassando una seconda risoluzione DNS), cosa che Playwright non espone facilmente da API pubblica — non implementato per restare nello scope del progetto.

### Scelte tecniche

- **Playwright invece di Selenium**: API più moderna, gestione automatica dei binari del browser, supporto nativo async.
- **`BackgroundTasks` invece di un broker esterno (Kafka/Redis)**: l'obiettivo era non far attendere il client durante la cattura, non costruire un sistema a eventi distribuito. `BackgroundTasks` risolve lo stesso problema restando nello stesso processo, senza infrastruttura aggiuntiva da configurare, testare e far girare in Docker — coerente con la scala di questo servizio (un solo worker, nessun bisogno di scalare orizzontalmente i consumer).
- **Job store in-memory invece di Redis/DB**: per un servizio a singolo processo è sufficiente; il costo è che lo stato dei job si perde a un riavvio, accettabile per questo caso d'uso.
- **Rate limit (`slowapi`) + semaforo di concorrenza**: sono due protezioni distinte e complementari. Il rate limit impedisce che un client spammi richieste (per IP, configurabile). Il semaforo limita quante istanze di Chromium girano contemporaneamente, indipendentemente da quante richieste sono arrivate: protegge la memoria del container anche da un singolo client che manda molte richieste legittime in sequenza.
- **Immagine base `mcr.microsoft.com/playwright/python`**: include già Chromium e tutte le dipendenze di sistema necessarie per l'headless, evitando di gestirle a mano nel Dockerfile.
- **uv** per la gestione delle dipendenze Python (locale e nel Dockerfile), al posto di pip/requirements.txt: è scritto in Rust, quindi risoluzione e installazione delle dipendenze sono molto più veloci di pip (specialmente sulla cache, praticamente istantanee), oltre a offrire lock file (`uv.lock`) per build riproducibili e gestione integrata delle versioni di Python.
- **Pre-check HTTP invece di ping ICMP**: un ping ICMP è spesso bloccato da firewall/provider cloud anche su siti perfettamente raggiungibili via HTTP, e richiede permessi elevati (socket raw) che il container non ha. Una richiesta `HEAD`/`GET` con timeout breve è più affidabile e coerente con ciò che Playwright farà comunque.
- **`tenacity` per il retry**: gestisce backoff esponenziale e condizioni di stop in modo testato, evitando di reimplementare a mano una logica facile da sbagliare (es. mancanza di jitter). Il retry è mirato solo ai timeout di Playwright, non agli URL già scartati dal pre-check.
- **`HEALTHCHECK` Docker su `/health`** ([Dockerfile](Dockerfile)): Docker interroga il servizio ogni 30s e marca il container `healthy`/`unhealthy` (visibile con `docker ps`) — utile per orchestratori/monitoring che devono sapere se riavviare il container. Nota: se il processo `uvicorn` muore del tutto, il container esce direttamente (`Exited`), non passa per lo stato `unhealthy`, che si vede invece solo se il processo resta vivo ma smette di rispondere.

## Struttura del progetto

```
.
├── .github/
│   └── workflows/
│       └── ci.yml            # Pipeline CI: build + test ad ogni push
├── app/
│   ├── main.py           # FastAPI app, endpoint, rate limit ed export file statici
│   ├── jobs.py             # Coda in-memory dei job, semaforo di concorrenza
│   ├── screenshot.py      # Logica di cattura screenshot (Playwright)
│   ├── utils.py            # Derivazione nome file da URL, check raggiungibilità
│   ├── security.py         # Protezione SSRF (blocco IP privati/riservati)
│   ├── config.py           # Configurazione (directory output, rate limit, ecc.)
│   ├── schemas.py          # Modelli Pydantic (request/response)
│   └── static/
│       └── index.html      # UI web minimale
├── tests/                    # Test automatici (pytest) — fuori da app/, non entra nell'immagine di produzione
├── screenshots/             # Output degli screenshot (montata come volume)
├── test-reports/            # Report HTML dei test (generato, non versionato)
├── Dockerfile                # Multi-stage: "runtime" (produzione) e "test"
├── docker-compose.yml
├── pyproject.toml           # Dipendenze del progetto (gestite con uv)
└── uv.lock
```

## Prerequisiti

- Docker e Docker Compose (per l'esecuzione containerizzata) — [Docker Desktop](https://www.docker.com/products/docker-desktop/) o [OrbStack](https://orbstack.dev/) su macOS
- [uv](https://docs.astral.sh/uv/) (solo per lo sviluppo locale, senza Docker). Per installarlo:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

## Setup ed esecuzione

Prima di tutto, scarica il progetto:

```bash
git clone <url-di-questo-repository>
cd url-screenshot-service
```

Poi scegli una delle due strade sotto — non serve seguirle entrambe.

### Con Docker (consigliato)

Non serve installare Python, Playwright o nient'altro: build dell'immagine e avvio in background (`-d` = detached, il terminale torna libero):

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

## Test automatici

I test (pytest) girano in un container Docker separato, basato su uno stage dedicato del [Dockerfile](Dockerfile) (`test`) che non fa parte dell'immagine di produzione — le dipendenze di test (`pytest`, `pytest-cov`, `pytest-html`) non vengono quindi mai spedite nell'immagine che gira in produzione (stage `runtime`).

**CI**: la suite gira automaticamente ad ogni push su GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) — stesso identico comando usato in locale, nessuna duplicazione di logica tra ambiente locale e pipeline. Il badge in cima al README riflette l'esito dell'ultima esecuzione.

```bash
docker compose --profile test run --build --rm tests
```

Il `--build` è importante: senza, `docker compose run` riusa l'immagine già costruita in precedenza (se esiste), quindi dopo aver modificato il codice i risultati potrebbero riflettere una versione vecchia.

Il container esegue la suite, genera due report in `test-reports/` (cartella montata sull'host, sopravvive alla chiusura del container) e si chiude da solo:
- `test-reports/report.html` — esito di ogni test (pytest-html)
- `test-reports/coverage/index.html` — percentuale di codice in `app/` effettivamente esercitata dai test, file per file (pytest-cov)

Il servizio `tests` ha `profiles: ["test"]`, quindi non parte mai con un normale `docker compose up`.

In locale, senza Docker:

```bash
uv run pytest                                    # solo i test
uv run pytest --cov=app --cov-report=term-missing  # con coverage a terminale
```

**Nota sulla coverage di `app/screenshot.py` (~33%, deliberatamente basso)**: la logica che apre davvero Chromium e cattura lo screenshot (`capture_screenshot`) non viene mai eseguita per davvero nei test — viene sempre sostituita con un mock (vedi `tests/test_jobs.py`, `tests/test_main.py`), per tenere la suite veloce, deterministica e senza dipendenze da un browser vero. Non è un buco da colmare: alzare questa percentuale richiederebbe test di integrazione che aprono un browser reale, volutamente fuori dallo scope di questa suite.

## Utilizzo e test manuale

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

> Se hai impostato `API_KEY`, aggiungi `-H "X-API-Key: <la-tua-chiave>"` a questa e alle altre richieste verso `/screenshot` e `/jobs` (non serve per `/health`), altrimenti la richiesta torna `401`.

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
# → {"id":"3f2...","url":"https://www.google.com/","status":"done","filename":"screenshot_www_google_com.png","error":null,"created_at":"..."}
```

Vedere l'intera coda:

```bash
curl http://localhost:8000/jobs
```

Recuperare l'immagine generata via HTTP (filename dallo stato del job):

```bash
curl -o out.png http://localhost:8000/screenshots/screenshot_www_google_com.png
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
| `API_KEY`                 | *(vuota)*            | Se impostata, richiede l'header `X-API-Key` su `POST /screenshot`, `GET /screenshot/{id}` e `GET /jobs`. Vuota di default: nessuna autenticazione, comodo per provare il servizio in locale — impostala per qualsiasi uso esposto pubblicamente |

