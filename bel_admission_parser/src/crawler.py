from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

KEYWORDS: tuple[str, ...] = (
    "приказ",
    "зачисл",
    "список",
    "абитуриент",
    "ход приема",
    "результаты",
)
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "target_urls.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def _normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.")


def _is_allowed_link(page_url: str, link_url: str) -> bool:
    parsed = urlparse(link_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    is_pdf = parsed.path.lower().endswith(".pdf")
    return is_pdf or _normalize_host(page_url) == _normalize_host(link_url)


async def _read_target_urls() -> list[str]:
    def read_json() -> Any:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)

    try:
        data = await asyncio.to_thread(read_json)
    except (OSError, json.JSONDecodeError, UnicodeError):
        return []

    if not isinstance(data, list):
        return []

    urls: list[str] = []
    for item in data:
        url: Any = item.get("url") if isinstance(item, dict) else item
        if isinstance(url, str) and urlparse(url).scheme in {"http", "https"}:
            urls.append(url)
    return list(dict.fromkeys(urls))


async def _crawl_site(
    client: httpx.AsyncClient,
    domain_url: str,
) -> tuple[str, list[str]]:
    try:
        response = await client.get(domain_url, follow_redirects=True)
        response.raise_for_status()
    except (
        httpx.TimeoutException,
        httpx.NetworkError,
        httpx.HTTPStatusError,
        httpx.InvalidURL,
        httpx.TooManyRedirects,
    ):
        return domain_url, []

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        links: list[str] = []

        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            text = anchor.get_text(" ", strip=True)
            searchable = f"{href} {text}".lower()

            if not href or not any(keyword in searchable for keyword in KEYWORDS):
                continue

            absolute_url = urljoin(str(response.url), href)
            if _is_allowed_link(str(response.url), absolute_url):
                links.append(absolute_url)

        return domain_url, list(dict.fromkeys(links))
    except (AttributeError, TypeError, ValueError, UnicodeError):
        return domain_url, []


async def find_admission_links() -> dict[str, list[str]]:
    target_urls = await _read_target_urls()
    if not target_urls:
        return {}

    timeout = httpx.Timeout(15.0)
    headers = {"User-Agent": USER_AGENT}

    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            results = await asyncio.gather(
                *(_crawl_site(client, url) for url in target_urls)
            )
    except (httpx.HTTPError, RuntimeError):
        return {url: [] for url in target_urls}

    return dict(results)
