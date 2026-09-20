from pydantic import BaseModel, HttpUrl

class ScreenshotRequest(BaseModel):
    url: HttpUrl

class ScreenshotResponse(BaseModel):
    filename: str
    path: str
