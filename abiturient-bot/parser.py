import io
import os
import time
import hashlib
import requests
from urllib.parse import urljoin, urlparse
from pypdf import PdfReader
from bs4 import BeautifulSoup
from config import CACHE_DIR, CACHE_TTL_HOURS


def get_cache_path(url: str) -> str:
    """Путь к кэш-файлу по хэшу URL"""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{url_hash}.cache")


def is_cache_valid(cache_path: str) -> bool:
    """Кэш живёт CACHE_TTL_HOURS часов"""
    if not os.path.exists(cache_path):
        return False
    file_age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
    return file_age_hours < CACHE_TTL_HOURS


def download_file(url: str) -> bytes:
    """Скачивает ЛЮБОЙ файл (страницу или PDF) с кэшем на 1 час"""
    cache_path = get_cache_path(url)

    if is_cache_valid(cache_path):
        with open(cache_path, "rb") as f:
            return f.read()

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    with open(cache_path, "wb") as f:
        f.write(response.content)

    return response.content


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Извлекает текст из PDF, не падает на пустых страницах"""
    # ИСПРАВЛЕНИЕ: PdfReader не принимает сырые байты, ему нужен
    # "файлоподобный объект". io.BytesIO превращает байты в "файл в памяти".
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


def extract_text_from_html(html_bytes: bytes) -> str:
    """Извлекает чистый текст из HTML"""
    html = html_bytes.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    for script in soup(["script", "style"]):
        script.decompose()

    return soup.get_text(separator="\n", strip=True)


def extract_pdf_links(html_bytes: bytes, base_url: str, filter_substring: str = "", max_links: int = 10) -> list:
    """Собирает ссылки на .pdf файлы со страницы"""
    html = html_bytes.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0].split("#")[0]
        if not href.lower().endswith(".pdf"):
            continue

        # urljoin собирает абсолютный URL из относительного:
        # "/sites/default/files/x.pdf" -> "https://www.brsu.by/sites/default/files/x.pdf"
        full_url = urljoin(base_url, href)

        if filter_substring and filter_substring.lower() not in full_url.lower():
            continue
        if full_url in links:
            continue

        links.append(full_url)
        if len(links) >= max_links:
            break

    return links


def extract_page_links(html_bytes: bytes, base_url: str, max_links: int = 6) -> list:
    """Собирает ссылки на внутренние страницы того же сайта (запасной уровень)"""
    html = html_bytes.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    base_host = urlparse(base_url).netloc
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0].split("#")[0]
        if href.lower().endswith(".pdf"):
            continue
        full_url = urljoin(base_url, href)
        if urlparse(full_url).netloc != base_host:
            continue
        if full_url == base_url or full_url in links:
            continue
        links.append(full_url)
        if len(links) >= max_links:
            break
    return links


def get_documents_from_source(source: dict) -> list:
    """
    Возвращает список документов источника: [{"url": ..., "text": ...}, ...]

    type "pdf"            -> источник сам является PDF, 1 документ
    type "html"           -> страница с текстом, 1 документ
    type "page_with_pdfs" -> страница-оглавление: ищем на ней ссылки на PDF,
                             скачиваем каждый -> несколько документов
    """
    try:
        source_type = source["type"]

        if source_type == "pdf":
            content = download_file(source["url"])
            return [{"url": source["url"], "text": extract_text_from_pdf(content)}]

        if source_type == "html":
            content = download_file(source["url"])
            return [{"url": source["url"], "text": extract_text_from_html(content)}]

        if source_type == "page_with_pdfs":
            page_bytes = download_file(source["url"])
            pdf_links = extract_pdf_links(
                page_bytes,
                source["url"],
                source.get("pdf_filter", ""),
                source.get("max_pdfs", 10),
            )

            # Предохранитель: если на странице-оглавлении нет прямых ссылок
            # на PDF, заглядываем на 1 уровень внутрь её ссылок (макс. 6 страниц)
            if not pdf_links:
                for sub_url in extract_page_links(page_bytes, source["url"]):
                    try:
                        sub_bytes = download_file(sub_url)
                    except Exception as e:
                        print(f"Ошибка при скачивании страницы {sub_url}: {e}")
                        continue
                    pdf_links.extend(extract_pdf_links(
                        sub_bytes, sub_url,
                        source.get("pdf_filter", ""),
                        source.get("max_pdfs", 10),
                    ))
                    if len(pdf_links) >= source.get("max_pdfs", 10):
                        pdf_links = pdf_links[:source.get("max_pdfs", 10)]
                        break

            documents = []
            for pdf_url in pdf_links:
                try:
                    pdf_bytes = download_file(pdf_url)
                    documents.append({"url": pdf_url, "text": extract_text_from_pdf(pdf_bytes)})
                except Exception as e:
                    print(f"Ошибка при скачивании PDF {pdf_url}: {e}")
            return documents

        print(f"Неизвестный тип источника: {source_type}")
        return []

    except Exception as e:
        print(f"Ошибка при обработке {source['url']}: {e}")
        return []