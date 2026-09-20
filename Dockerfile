FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy AS base

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./


FROM base AS test

RUN uv sync --frozen --no-cache
COPY app ./app
COPY tests ./tests

CMD ["uv", "run", "pytest", "--html=/app/test-reports/report.html", "--self-contained-html"]


FROM base AS runtime

RUN uv sync --frozen --no-dev --no-cache
COPY app ./app

RUN mkdir -p /app/screenshots

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
