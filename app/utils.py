import httpx


def url_to_filename(url: str) -> str:
    """Deriva un nome file sicuro dall'URL (es. https://google.com -> screenshot_google_com.png)."""
    return "screenshot_" + url.split("//")[-1].split("/")[0] + ".png"


async def is_reachable(url: str, timeout: float = 5.0) -> bool:
    """Verifica se l'URL risponde via HTTP prima di avviare Playwright."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.head(url)
            if response.status_code == 405:  # alcuni server non supportano HEAD
                response = await client.get(url)
            return response.status_code < 400
    except httpx.RequestError:
        return False
