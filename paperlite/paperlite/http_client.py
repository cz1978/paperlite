from __future__ import annotations

import httpx

PAPERLITE_USER_AGENT = "PaperLite/0.1 (+https://github.com/paperlite; feed health check)"
BROWSER_COMPAT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

FEED_ACCEPT = "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"
BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,application/rss+xml;q=0.8,*/*;q=0.7"


def feed_headers(request_profile: str = "paperlite") -> dict[str, str]:
    profile = str(request_profile or "paperlite").strip().lower()
    if profile == "browser_compat":
        return {
            "accept": BROWSER_ACCEPT,
            "accept-language": "en-US,en;q=0.9",
            "user-agent": BROWSER_COMPAT_USER_AGENT,
        }
    if profile != "paperlite":
        raise ValueError("unknown request profile: " + str(request_profile))
    return {
        "accept": FEED_ACCEPT,
        "accept-language": "en-US,en;q=0.9",
        "user-agent": PAPERLITE_USER_AGENT,
    }


def get_feed_url(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    request_profile: str = "paperlite",
) -> httpx.Response:
    return httpx.get(
        url,
        timeout=timeout_seconds,
        follow_redirects=True,
        headers=feed_headers(request_profile),
    )
