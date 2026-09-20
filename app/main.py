import logging
import os

from fastapi import FastAPI
from pydantic import BaseModel, HttpUrl

from app.config import SCREENSHOTS_DIR
from app.screenshot import capture_screenshot
from app.utils import url_to_filename

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="URL Screenshot Service")


class ScreenshotRequest(BaseModel):
    url: HttpUrl


class ScreenshotResponse(BaseModel):
    filename: str
    path: str


@app.on_event("startup")
def ensure_screenshots_dir() -> None:
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/screenshot", response_model=ScreenshotResponse)
async def screenshot(request: ScreenshotRequest) -> ScreenshotResponse:
    # TODO: generare il filename, chiamare capture_screenshot, gestire errori/logging
    raise NotImplementedError
