from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Iterable
from html import escape
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from .crawler import scan_university
from .ocr_parser import extract_text_from_url
from .search import SearchMatch, parse_search_queries, search_surname

router = Router()
MAX_MESSAGE_LENGTH = 4000
CONFIG_PATH = Path(__file__).parent.parent / "config" / "target_urls.json"


def load_universities() -> dict[str, str]:
    fallback = {"bsu.by": "БГУ", "bsuir.by": "БГУИР"}
    if not CONFIG_PATH.exists():
        return fallback

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            data: Any = json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError):
        logging.exception("Не удалось загрузить список вузов из %s", CONFIG_PATH)
        return fallback

    universities: dict[str, str] = {}
    if isinstance(data, dict):
        for domain, name in data.items():
            if isinstance(domain, str) and isinstance(name, str):
                host = (urlparse(domain).hostname or domain).removeprefix("www.")
                universities[host.lower()] = name
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                host = (urlparse(item).hostname or "").removeprefix("www.")
                if host:
                    universities[host.lower()] = host
            elif isinstance(item, dict):
                url = item.get("url")
                name = item.get("name") or item.get("full_name")
                if isinstance(url, str) and isinstance(name, str):
                    host = (urlparse(url).hostname or "").removeprefix("www.")
                    if host:
                        universities[host.lower()] = name

    return universities or fallback


UNIVERSITIES = load_universities()


def _split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> Iterable[str]:
    while len(text) > limit:
        split_at = text.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        yield text[:split_at]
        text = text[split_at:].lstrip("\n")
    if text:
        yield text


def _university_name(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host in UNIVERSITIES:
        return UNIVERSITIES[host]

    filename = unquote(PurePosixPath(parsed.path).stem).replace("_", " ").strip()
    return filename or host or "Неизвестное учебное заведение"


async def _search_url(
    url: str,
    queries: list[str],
) -> tuple[str, dict[str, list[SearchMatch]]]:
    try:
        text = await extract_text_from_url(url)
        matches = await asyncio.to_thread(search_surname, text, queries)
        return url, matches
    except Exception:
        logging.exception("Не удалось обработать ссылку %s", url)
        return url, {query: [] for query in queries}


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "Привет! Отправь мне фамилию для поиска в базах зачисленных"
    )


@router.message()
async def surname_handler(message: Message) -> None:
    query_text = (message.text or "").strip()
    queries = parse_search_queries(query_text)
    if not queries:
        await message.answer("Отправь фамилии или имена текстовым сообщением.")
        return

    await message.answer("Ищу совпадения по сайтам...")

    try:
        links_by_domain = await scan_university()
        links = list(
            dict.fromkeys(
                link
                for domain_links in links_by_domain.values()
                for link in domain_links
            )
        )

        if not links:
            await message.answer("Ссылки на списки зачисленных не найдены.")
            return

        results = await asyncio.gather(
            *(_search_url(url, queries) for url in links)
        )
        grouped: dict[str, list[tuple[str, SearchMatch]]] = {
            query: [] for query in queries
        }
        for url, matches_by_query in results:
            for query, matches in matches_by_query.items():
                grouped[query].extend((url, match) for match in matches)

        if not any(grouped.values()):
            await message.answer(
                "Совпадений для указанных фамилий и имён не найдено."
            )
            return

        response_parts: list[str] = []
        for query, matches in grouped.items():
            response_parts.append(
                f"🎯 <b>Результаты поиска:</b> {escape(query)}"
            )
            if not matches:
                response_parts.append("❌ Совпадений нет")
                continue

            for url, match in matches:
                university = escape(_university_name(url))
                heading = escape(match["heading"] or "Не определена")
                line = escape(match["line"])
                safe_url = escape(url, quote=True)
                response_parts.extend(
                    [
                        "",
                        f"🏛 <b>Учебное заведение:</b> {university}",
                        f"📚 <b>Специальность/Факультет:</b> {heading}",
                        f"✅ <b>Статус в списке:</b> {line}",
                        (
                            "🔗 <b>Источник:</b> "
                            f'<a href="{safe_url}">Открыть список зачисленных</a>'
                        ),
                    ]
                )
            response_parts.append("")

        response = "\n".join(response_parts)
        for chunk in _split_message(response):
            await message.answer(
                chunk,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    except Exception:
        logging.exception("Ошибка при поиске фамилии")
        await message.answer("Во время поиска произошла ошибка. Попробуй позже.")


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Переменная окружения BOT_TOKEN не задана")

    bot = Bot(token=token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    info = await bot.get_webhook_info()
    logging.info(
        "Webhook: %s, pending: %s",
        info.url,
        info.pending_update_count,
    )
    await bot.delete_webhook(drop_pending_updates=True)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
