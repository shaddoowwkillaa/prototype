from __future__ import annotations

import asyncio
import gc
import json
import logging
import socket
import ssl
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

KEYWORDS: tuple[str, ...] = (
    "приказ о зачислении",
    "список зачисленных",
    "зачисленные",
    "итоги приема",
    "результаты зачисления",
    "списки абитуриентов",
    "поступившие",
)
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "target_urls.json"
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}
MAX_FILE_SIZE = 10 * 1024 * 1024
REQUEST_DELAY = 0.3


def _normalize_host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return host.removeprefix("www.")


def _is_pdf(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _is_allowed_link(page_url: str, link_url: str) -> bool:
    parsed = urlparse(link_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return _is_pdf(link_url) or _normalize_host(page_url) == _normalize_host(link_url)


async def _read_target_urls() -> list[str]:
    def read_json() -> Any:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)

    try:
        data = await asyncio.to_thread(read_json)
    except (OSError, UnicodeError, json.JSONDecodeError):
        logging.exception("Не удалось прочитать %s", CONFIG_PATH)
        return []

    if not isinstance(data, list):
        return []

    urls: list[str] = []
    for item in data:
        url: Any = item.get("url") if isinstance(item, dict) else item
        if isinstance(url, str) and urlparse(url).scheme in {"http", "https"}:
            urls.append(url)
    return list(dict.fromkeys(urls))


async def _pdf_is_allowed(session: aiohttp.ClientSession, url: str) -> bool:
    try:
        async with session.head(url, allow_redirects=True) as response:
            if response.status == 405:
                async with session.get(url, allow_redirects=True) as get_response:
                    get_response.raise_for_status()
                    content_length = get_response.content_length
            else:
                response.raise_for_status()
                content_length = response.content_length

            if content_length is not None and content_length > MAX_FILE_SIZE:
                logging.warning("PDF больше 10 МБ пропущен: %s", url)
                return False
            return True
    except (aiohttp.ClientError, asyncio.TimeoutError):
        logging.warning("Не удалось проверить PDF: %s", url)
        return False
    finally:
        gc.collect()
        await asyncio.sleep(REQUEST_DELAY)


async def _crawl_site(
    session: aiohttp.ClientSession,
    domain_url: str,
) -> tuple[str, list[str]]:
    # ЕСЛИ СРАЗУ УКАЗАН PDF-ФАЙЛ — возвращаем его напрямую без лишнего поиска!
    if _is_pdf(domain_url):
        return domain_url, [domain_url]

    try:
        async with session.get(domain_url, allow_redirects=True) as response:
            if response.status != 200:
                logging.warning(
                    "Сайт %s вернул HTTP %s (итоговый URL: %s)",
                    domain_url,
                    response.status,
                    response.url,
                )
                return domain_url, []
            page_url = str(response.url)
            html = await response.text(errors="ignore")
    except asyncio.TimeoutError:
        logging.warning("Тайм-аут при загрузке сайта: %s", domain_url)
        return domain_url, []
    except aiohttp.ClientConnectorError as error:
        logging.warning("Ошибка подключения к %s: %s", domain_url, error)
        return domain_url, []
    except aiohttp.ClientError as error:
        logging.warning("HTTP-ошибка при загрузке %s: %s", domain_url, error)
        return domain_url, []
    except UnicodeError as error:
        logging.warning("Ошибка декодирования ответа %s: %s", domain_url, error)
        return domain_url, []
    finally:
        await asyncio.sleep(REQUEST_DELAY)

    soup: BeautifulSoup | None = None
    try:
        soup = BeautifulSoup(html, "html.parser")
        candidates: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            searchable = f"{href} {anchor.get_text(' ', strip=True)}".lower()
            if not href or not any(keyword in searchable for keyword in KEYWORDS):
                continue

            absolute_url = urljoin(page_url, href)
            if _is_allowed_link(page_url, absolute_url):
                candidates.append(absolute_url)

        links: list[str] = []
        for link in dict.fromkeys(candidates):
            if not _is_pdf(link) or await _pdf_is_allowed(session, link):
                links.append(link)
        return domain_url, links
    except (AttributeError, TypeError, ValueError, UnicodeError):
        logging.exception("Ошибка разбора страницы: %s", domain_url)
        return domain_url, []
    finally:
        soup = None
        html = ""
        gc.collect()


async def scan_university() -> dict[str, list[str]]:
    target_urls = await _read_target_urls()
    if not target_urls:
        return {}

    timeout = aiohttp.ClientTimeout(
        total=20,
        connect=10,
        sock_connect=10,
        sock_read=20,
    )
    
    # Создаем SSL-контекст прямо здесь (внутри запущенного event loop)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(
        limit=3,
        ttl_dns_cache=300,
        family=socket.AF_INET,
        ssl=ssl_context,  # Безопасно передаем отключение проверки сертификатов
    )

    try:
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers=BROWSER_HEADERS,
        ) as session:
            results: list[tuple[str, list[str]]] = []
            for offset in range(0, len(target_urls), 3):
                batch = target_urls[offset : offset + 3]
                batch_results = await asyncio.gather(
                    *(_crawl_site(session, url) for url in batch)
                )
                results.extend(batch_results)
                await asyncio.sleep(REQUEST_DELAY)
    except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError):
        logging.exception("Ошибка во время обхода сайтов")
        return {url: [] for url in target_urls}

    return dict(results)