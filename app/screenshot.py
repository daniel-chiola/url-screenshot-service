from playwright.async_api import async_playwright


async def capture_screenshot(url: str, output_path: str) -> None:
    """Apre l'URL con Chromium headless e salva lo screenshot in output_path."""
    p = await async_playwright().__aenter__()
    browser = await p.chromium.launch()
    page = await browser.new_page()
    await page.goto(url)
    await page.screenshot(path=output_path)
    await browser.close()
