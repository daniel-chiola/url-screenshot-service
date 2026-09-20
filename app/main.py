import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import SCREENSHOTS_DIR
from app.schemas import ScreenshotRequest, ScreenshotResponse
from app.screenshot import capture_screenshot
from app.utils import url_to_filename

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    yield


app = FastAPI(title="URL Screenshot Service", lifespan=lifespan)


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
