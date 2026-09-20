"""Cattura screenshot di pagine web con Chromium headless (Playwright)."""

from playwright.async_api import Route
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.logger import app_logger
from app.security import is_safe_url

# Pattern minimi per bloccare i principali network pubblicitari/di tracking più comuni.
AD_URL_PATTERNS = (
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "adservice.google.com",
    "adnxs.com",
    "taboola.com",
    "outbrain.com",
)


def _make_route_guard(block_ads: bool):
    async def guard(route: Route) -> None:
        request = route.request
        # Controlliamo l'indirizzo anche qui, non solo prima di iniziare: un URL pubblico
        # potrebbe reindirizzare (redirect) verso un indirizzo interno una volta aperto,
        # e ogni redirect passa di nuovo da qui perché genera una nuova navigazione.
        if request.resource_type == "document" and not await is_safe_url(request.url):
            app_logger.redirect_blocked(request.url)
            await route.abort()
            return
        if block_ads and any(pattern in request.url for pattern in AD_URL_PATTERNS):
            await route.abort()
            return
        await route.continue_()

    return guard


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    retry=retry_if_exception_type(PlaywrightTimeoutError),
)
async def capture_screenshot(
    url: str,
    output_path: str,
    width: int = 1280,
    height: int = 800,
    full_page: bool = False,
    dark_mode: bool = False,
    block_ads: bool = True,
) -> None:
    """Apre l'URL con Chromium headless e salva lo screenshot in output_path."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            page = await browser.new_page(
                viewport={"width": width, "height": height},
                color_scheme="dark" if dark_mode else "light",
            )
            await page.route("**/*", _make_route_guard(block_ads))
            await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            await page.screenshot(path=output_path, full_page=full_page, type="jpeg", quality=80, animations="disabled")
        finally:
            await browser.close()
