import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import SCREENSHOTS_DIR
from app.schemas import ScreenshotRequest, ScreenshotResponse
from app.screenshot import capture_screenshot
from app.utils import url_to_filename

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

app = FastAPI(title="URL Screenshot Service")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/screenshot", response_model=ScreenshotResponse)
async def screenshot(request: ScreenshotRequest) -> ScreenshotResponse:
    url = str(request.url)
    filename = url_to_filename(url)
    output_path = os.path.join(SCREENSHOTS_DIR, filename)
    await capture_screenshot(url, output_path)
    return ScreenshotResponse(filename=filename, path=output_path)


app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
