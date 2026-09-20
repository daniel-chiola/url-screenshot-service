from pydantic import BaseModel, HttpUrl

class ScreenshotRequest(BaseModel):
    """Corpo della richiesta POST /screenshot."""
    url: HttpUrl
    width: int = 1280
    height: int = 800
    full_page: bool = False
    dark_mode: bool = False
    block_ads: bool = True


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
