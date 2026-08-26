import re
from parser import get_documents_from_source
from config import CONTEXT_LENGTH


def normalize_text(text: str) -> str:
    """Нормализация: нижний регистр, ё→е, лишние пробелы"""
    text = text.lower()
    text = text.replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def generate_search_variants(full_name: str) -> list:
    """Варианты ФИО: полное, фамилия+имя, фамилия+инициалы"""
    parts = full_name.strip().split()
    if len(parts) < 2:
        return [normalize_text(full_name)]

    surname = parts[0]
    name = parts[1]
    patronymic = parts[2] if len(parts) > 2 else ""

    variants = [
        normalize_text(full_name),
        normalize_text(f"{surname} {name}"),
    ]

    if patronymic:
        variants.extend([
            normalize_text(f"{surname} {name[0]}. {patronymic[0]}."),
            normalize_text(f"{surname} {name[0]} {patronymic[0]}"),
        ])

    return variants


def extract_context(text: str, match_pos: int, context_length: int = CONTEXT_LENGTH) -> str:
    """Контекст вокруг найденного ФИО"""
    start = max(0, match_pos - context_length)
    end = min(len(text), match_pos + context_length)
    return text[start:end]


def search_in_text(text: str, search_variants: list) -> list:
    """Ищет варианты ФИО, НЕ дублируя совпадения"""
    normalized_text = normalize_text(text)
    found_spans = []
    results = []

    # Сначала самые длинные варианты (полное ФИО), чтобы
    # "фамилия имя" не давало второе совпадение внутри того же фрагмента
    for variant in sorted(search_variants, key=len, reverse=True):
        for match in re.finditer(re.escape(variant), normalized_text):
            start, end = match.start(), match.end()
            # Если это совпадение уже покрыто более длинным вариантом — пропускаем
            if any(s <= start and end <= e for s, e in found_spans):
                continue
            found_spans.append((start, end))
            results.append({
                "variant": variant,
                "context": extract_context(text, start),
            })

    return results


def extract_specialty_from_context(context: str) -> str:
    """Пока простая версия: ищет ключевые слова рядом с ФИО"""
    keywords = ["специальность", "факультет", "группа", "направление"]

    for keyword in keywords:
        if keyword in context.lower():
            match = re.search(rf"{keyword}[:\s]+([^\n]+)", context, re.IGNORECASE)
            if match:
                return match.group(1).strip()

    return "Не удалось определить"


def search_student(full_name: str, sources: list) -> list:
    """Ищет студента во всех источниках и во всех их документах"""
    search_variants = generate_search_variants(full_name)
    results = []

    for source in sources:
        documents = get_documents_from_source(source)

        for doc in documents:
            if not doc["text"]:
                continue

            for match in search_in_text(doc["text"], search_variants):
                results.append({
                    "university": source["university"],
                    "year": source["year"],
                    "description": source["description"],
                    "specialty": extract_specialty_from_context(match["context"]),
                    "source_url": source["url"],
                    "file_url": doc["url"],
                    "context": match["context"],
                })

    return results