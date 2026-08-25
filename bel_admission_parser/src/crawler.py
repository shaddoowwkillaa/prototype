import io
import logging
import asyncio
from urllib.parse import urljoin, urlparse
import aiohttp
from bs4 import BeautifulSoup
import pdfplumber

# Настройка логирования для отслеживания в Render
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Ключевые слова для фильтрации целевых ссылок
TARGET_KEYWORDS = [
    # Русскоязычные корни и слова
    'абитуриент',   # Покроет: абитуриенту, абитуриентам, абитуриентский
    'поступл',      # Покроет: поступление, поступающим, поступать
    'приемн',       # Покроет: приемная комиссия, прием
    'зачисл',       # Покроет: зачисление, зачисленные, зачислен
    'список',       # Покроет: список, списки
    'ход',          # Покроет: ход подачи документов
    'колл',         # Покроет: колледж, колледжа
    'дневн',        # Покроет: дневное, дневная
    'заочн',        # Покроет: заочное, заочная
    'бюджет',       # Покроет: бюджетная форма
    'платн',        # Покроет: платная форма, платники
    'результ',      # Покроет: результаты, результат
    'свед',         # Покроет: сведения о зачислении

    # Транслит и англоязычные URL-адреса
    'abi', 'abitur', 'priem', 'postup', 'zachislen', 
    'spisok', 'spiski', 'pdf', 'result', 'doc'
]

async def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Извлечение текста из PDF в фоновом потоке без блокировки asyncio."""
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
        return text

    return await asyncio.to_thread(parse_pdf)

async def scan_university(start_url: str, surname: str, max_depth: int = 2) -> list[str]:
    """Рекурсивный поиск фамилии на страницах ВУЗа и внутри PDF-документов."""
    visited = set()
    found_urls = []
    surname_lower = surname.strip().lower()
    base_domain = urlparse(start_url).netloc

    logging.info(f"🔎 Старт поиска для: '{surname}' на {start_url}")

    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:

        async def parse(url: str, current_depth: int):
            if url in visited or current_depth > max_depth:
                return
            visited.add(url)

            logging.info(f"  [Уровень {current_depth}] Сканирование: {url}")

            try:
                async with session.get(url, timeout=15, ssl=False) as response:
                    if response.status != 200:
                        logging.warning(f"  ⚠️ Ошибка {response.status} на {url}")
                        return

                    content_type = response.headers.get("Content-Type", "").lower()

                    # 1. Проверка PDF-документов
                    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                        logging.info(f"  📄 Чтение PDF: {url}")
                        pdf_bytes = await response.read()
                        pdf_text = await _extract_pdf_text(pdf_bytes)
                        if surname_lower in pdf_text.lower():
                            logging.info(f"  ✅ НАЙДЕНО В PDF: {url}")
                            found_urls.append(url)
                        return

                    # 2. Проверка обычных HTML-страниц
                    html = await response.text(errors="ignore")
                    soup = BeautifulSoup(html, "html.parser")
                    text_content = soup.get_text()

                    if surname_lower in text_content.lower():
                        logging.info(f"  ✅ НАЙДЕНО НА СТРАНИЦЕ: {url}")
                        found_urls.append(url)

                    # 3. Поиск ссылок для перехода на уровень 2
                    if current_depth < max_depth:
                        links_to_visit = []
                        for a_tag in soup.find_all("a", href=True):
                            href = a_tag["href"].strip()
                            full_url = urljoin(url, href)
                            parsed_target = urlparse(full_url)

                            # Переходим только по ссылкам текущего домена с релевантными ключевыми словами
                            if parsed_target.netloc == base_domain:
                                link_text = a_tag.get_text().lower()
                                link_url_lower = full_url.lower()

                                if any(kw in link_url_lower or kw in link_text for kw in TARGET_KEYWORDS):
                                    if full_url not in visited:
                                        links_to_visit.append(full_url)

                        # Ограничиваем количество переходов для экономии ресурсов Render
                        for next_url in links_to_visit[:6]:
                            await parse(next_url, current_depth + 1)

            except Exception as e:
                logging.error(f"  ❌ Ошибка загрузки {url}: {e}")

        await parse(start_url, 1)

    return found_urls