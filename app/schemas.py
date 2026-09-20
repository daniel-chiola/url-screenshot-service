from pydantic import BaseModel, HttpUrl


class ScreenshotRequest(BaseModel):
    """Corpo della richiesta POST /screenshot."""

    url: HttpUrl


class JobResponse(BaseModel):
    """Risposta immediata alla creazione di un job (POST /screenshot)."""

    id: str
    status: str


class JobDetail(BaseModel):
    """Stato completo di un job (GET /screenshot/{id}, GET /jobs)."""

    id: str
    url: str
    status: str
    filename: str | None = None
    error: str | None = None
    created_at: str
