import io
import gc
import logging
import asyncio
from urllib.parse import urljoin, urlparse
import aiohttp
from bs4 import BeautifulSoup
import pdfplumber

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

TARGET_KEYWORDS = [
    'абитуриент', 'поступл', 'приемн', 'зачисл', 'список', 'ход', 
    'колл', 'дневн', 'заочн', 'бюджет', 'платн', 'результ', 'свед',
    'abi', 'abitur', 'priem', 'postup', 'zachislen', 'spisok', 'spiski', 'pdf'
]

async def _extract_pdf_text(pdf_bytes: bytes) -> str:
    def parse_pdf():
        text = ""
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            logging.error(f"  ❌ Ошибка чтения PDF: {e}")
        finally:
            gc.collect()  # Освобождаем RAM после каждого PDF
        return text

    return await asyncio.to_thread(parse_pdf)

async def scan_university(start_url: str, surname: str, max_depth: int = 2) -> list[str]:
    visited = set()
    found_urls = []
    surname_lower = surname.strip().lower()
    base_domain = urlparse(start_url).netloc

    logging.info(f"🔎 Старт поиска для: '{surname}' на {start_url}")

    # Ограничиваем количество одновременных соединений (не больше 3)
    connector = aiohttp.TCPConnector(limit=3)
    async with aiohttp.ClientSession(connector=connector, headers={"User-Agent": "Mozilla/5.0"}) as session:

        async def parse(url: str, current_depth: int):
            if url in visited or current_depth > max_depth:
                return
            visited.add(url)

            logging.info(f"  [Уровень {current_depth}] Сканирование: {url}")
            await asyncio.sleep(0.3)  # Пауза для снижения нагрузки на CPU/RAM

            try:
                async with session.get(url, timeout=12, ssl=False) as response:
                    if response.status != 200:
                        return

                    # Проверка размера файла (игнорируем гигабайтные сканы)
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > 10 * 1024 * 1024:
                        logging.warning(f"  ⚠️ Файл слишком большой (>10MB), пропуск: {url}")
                        return

                    content_type = response.headers.get("Content-Type", "").lower()

                    # 1. Проверка PDF
                    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                        logging.info(f"  📄 Чтение PDF: {url}")
                        pdf_bytes = await response.read()
                        pdf_text = await _extract_pdf_text(pdf_bytes)
                        del pdf_bytes  # Очищаем бинарные данные из памяти
                        
                        if surname_lower in pdf_text.lower():
                            logging.info(f"  ✅ НАЙДЕНО В PDF: {url}")
                            found_urls.append(url)
                        return

                    # 2. Проверка HTML
                    html = await response.text(errors="ignore")
                    soup = BeautifulSoup(html, "html.parser")
                    text_content = soup.get_text()

                    if surname_lower in text_content.lower():
                        logging.info(f"  ✅ НАЙДЕНО НА СТРАНИЦЕ: {url}")
                        found_urls.append(url)

                    # 3. Переход по ссылкам
                    if current_depth < max_depth:
                        links_to_visit = []
                        for a_tag in soup.find_all("a", href=True):
                            href = a_tag["href"].strip()
                            full_url = urljoin(url, href)
                            parsed_target = urlparse(full_url)

                            if parsed_target.netloc == base_domain:
                                link_text = a_tag.get_text().lower()
                                link_url_lower = full_url.lower()

                                if any(kw in link_url_lower or kw in link_text for kw in TARGET_KEYWORDS):
                                    if full_url not in visited:
                                        links_to_visit.append(full_url)

                        for next_url in links_to_visit[:4]:
                            await parse(next_url, current_depth + 1)

            except Exception as e:
                logging.error(f"  ❌ Ошибка загрузки {url}: {e}")

        await parse(start_url, 1)

    return found_urls