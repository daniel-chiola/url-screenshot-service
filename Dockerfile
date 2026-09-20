FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy AS base

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./


FROM base AS test

RUN uv sync --frozen --no-cache
COPY app ./app
COPY tests ./tests

CMD ["uv", "run", "--frozen", "pytest", \
     "--html=/app/test-reports/report.html", "--self-contained-html", \
     "--cov=app", "--cov-report=term-missing", "--cov-report=html:/app/test-reports/coverage"]


FROM base AS runtime

# uv scarica un proprio interprete Python gestito (il Python di sistema dell'immagine
# è troppo vecchio per i nostri vincoli). Di default lo installa fuori da /app (nella
# home dell'utente che esegue la build, qui root) — spostandolo dentro /app, il chown
# qui sotto lo rende accessibile anche a pwuser, l'utente non-root con cui gira il container.
ENV UV_PYTHON_INSTALL_DIR=/app/.uv-python

# Installiamo le dipendenze di produzione
RUN uv sync --frozen --no-dev --no-cache

# Copiamo il codice dell'applicazione
COPY app ./app

# Creiamo la cartella per gli screenshot e assegniamo la proprietà a 'pwuser'
# (pwuser è l'utente non-root preconfigurato nell'immagine di Playwright)
RUN mkdir -p /app/screenshots && chown -R pwuser:pwuser /app

EXPOSE 8000

# Health check docker: il container risponde con 200 OK se il servizio è attivo
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
  CMD curl -f http://localhost:8000/health || exit 1
# Cambiamo l'utente per l'esecuzione, applicando il principio del minimo privilegio
USER pwuser

CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
