import hashlib
import json
import io
from pathlib import Path
import httpx
from bs4 import BeautifulSoup
import pdfplumber

try:
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(use_angle_cls=True, lang='ru', show_log=False)
except Exception:
    ocr = None

CACHE_FILE = Path("data/cache.json")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def _get_bytes_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()

def _load_cache() -> dict[str, str]:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_cache(cache: dict[str, str]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def _parse_pdf(pdf_bytes: bytes) -> str:
    extracted_text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
        
        # Если pdfplumber не нашел текст, пробуем OCR
        if not extracted_text.strip() and ocr is not None:
            # Для работы PaddleOCR с PDF требуется конвертация страниц в изображения
            results = ocr.ocr(pdf_bytes, cls=True)
            ocr_lines = []
            if results:
                for page in results:
                    if page:
                        for line in page:
                            ocr_lines.append(line[1][0])
            extracted_text = "\n".join(ocr_lines)
    except Exception:
        pass
    return extracted_text

def _parse_html(html_text: str) -> str:
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        for element in soup(["script", "style", "header", "footer", "nav"]):
            element.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception:
        return ""

async def extract_text_from_url(url: str) -> str:
    """Извлекает текст из HTML или PDF по указанной ссылке с использованием кэша."""
    try:
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content

        content_hash = _get_bytes_hash(content)
        cache = _load_cache()

        if content_hash in cache:
            return cache[content_hash]

        is_pdf = url.lower().endswith('.pdf') or 'application/pdf' in response.headers.get('Content-Type', '')

        if is_pdf:
            text = _parse_pdf(content)
        else:
            text = _parse_html(response.text)

        if text.strip():
            cache[content_hash] = text
            _save_cache(cache)

        return text
    except Exception:
        return ""