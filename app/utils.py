def url_to_filename(url: str) -> str:
    """Deriva un nome file sicuro dall'URL (es. https://google.com -> screenshot_google_com.png)."""
    return "screenshot_" + url.split("//")[-1].split("/")[0] + ".png"
