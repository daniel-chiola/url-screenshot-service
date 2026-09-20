import logging
import os

from fastapi import FastAPI

from app.config import SCREENSHOTS_DIR
from app.schemas import ScreenshotRequest, ScreenshotResponse
from app.screenshot import capture_screenshot
from app.utils import url_to_filename

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="URL Screenshot Service")


@app.lifespan("startup")
def ensure_screenshots_dir() -> None:
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/screenshot", response_model=ScreenshotResponse)
async def screenshot(request: ScreenshotRequest) -> ScreenshotResponse:
    filename = url_to_filename(request.url)
    output_path = os.path.join(SCREENSHOTS_DIR, filename)
    capture_screenshot(request.url, output_path)
    return ScreenshotResponse(filename=filename, path=output_path)
