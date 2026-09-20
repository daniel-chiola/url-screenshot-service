"""Cattura screenshot di pagine web con Chromium headless (Playwright)."""

from playwright.async_api import Route
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

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


async def _block_ads(route: Route) -> None:
    if any(pattern in route.request.url for pattern in AD_URL_PATTERNS):
        await route.abort()
    else:
        await route.continue_()


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
            if block_ads:
                await page.route("**/*", _block_ads)
            await page.goto(url)
            await page.screenshot(path=output_path, full_page=full_page)
        finally:
            await browser.close()
