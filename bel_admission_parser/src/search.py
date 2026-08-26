from __future__ import annotations

import re
from typing import Any, TypedDict

from rapidfuzz import fuzz, process

_QUERY_SEPARATOR = re.compile(r"\s*(?:,|\n|\s+и\s+)\s*", re.IGNORECASE)
_WORD_RE = re.compile(r"[а-яa-z]+", re.IGNORECASE)
_HEADING_WORDS = (
    "специальност",
    "факультет",
    "институт",
    "кафедр",
    "направлен",
    "профиль",
    "образовательная программа",
)


class SearchMatch(TypedDict):
    line: str
    heading: str | None
    score: float


def _normalize(value: str) -> str:
    value = value.lower().replace("ё", "е")
    return " ".join(_WORD_RE.findall(value))


def parse_search_queries(queries: str | list[str]) -> list[str]:
    raw_values = [queries] if isinstance(queries, str) else queries
    parsed: list[str] = []
    seen: set[str] = set()

    for value in raw_values:
        if not isinstance(value, str):
            continue
        for part in _QUERY_SEPARATOR.split(value):
            query = " ".join(part.split()).strip(" ,;")
            normalized = _normalize(query)
            if normalized and normalized not in seen:
                seen.add(normalized)
                parsed.append(query)

    return parsed


def _match_score(query: str, line: str, **_: Any) -> float:
    query_words = _WORD_RE.findall(query.lower().replace("ё", "е"))
    line_words = _WORD_RE.findall(line.lower().replace("ё", "е"))
    if not query_words or not line_words:
        return 0.0

    # 1. ЖЕСТКИЙ ПРИОРИТЕТ: Ищем совпадение для Фамилии (первое слово запроса)
    surname_score = max(
        (fuzz.ratio(query_words[0], word) for word in line_words),
        default=0.0,
    )
    
    # Если фамилия совпала меньше чем на 75%, сразу отбраковываем строку
    if surname_score < 75.0:
        return 0.0

    # Если в запросе была только фамилия, возвращаем её балл
    if len(query_words) == 1:
        return surname_score

    # 2. Ищем имя и отчество строго после найденной фамилии в строке
    try:
        surname_index = max(
            range(len(line_words)),
            key=lambda index: fuzz.ratio(query_words[0], line_words[index]),
        )
    except ValueError:
        return 0.0

    following_words = line_words[surname_index + 1 : surname_index + len(query_words)]
    if not following_words:
        return surname_score * 0.8

    name_scores = [
        100.0
        if len(expected) == 1 and actual.startswith(expected)
        else float(fuzz.ratio(expected, actual))
        for expected, actual in zip(query_words[1:], following_words)
    ]
    
    return min([float(surname_score), *name_scores])


def _find_heading(lines: list[str], match_index: int) -> str | None:
    for index in range(match_index - 1, max(-1, match_index - 10), -1):
        candidate = lines[index].strip()
        normalized = _normalize(candidate)
        if not normalized or len(candidate) > 180:
            continue
        if any(word in normalized for word in _HEADING_WORDS):
            return candidate
        if not re.search(r"\d", candidate) and 1 < len(normalized.split()) <= 12:
            return candidate
    return None


def search_surname(
    text: str,
    surname: str | list[str],
    threshold: int = 70,  # Снижаем порог до 70 для надежности
) -> dict[str, list[SearchMatch]]:
    queries = parse_search_queries(surname)
    results: dict[str, list[SearchMatch]] = {query: [] for query in queries}
    
    # Нормализуем весь текст: убираем лишние пробелы, приводя к ровному виду
    cleaned_text = " ".join(text.split())
    
    # Также сохраняем оригинальные строки для вывода
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not queries:
        return results

    for query in queries:
        query_lower = query.lower().replace("ё", "е")
        query_words = _WORD_RE.findall(query_lower)
        if not query_words:
            continue
            
        target_surname = query_words[0]
        found_matches = []

        # Проходим по каждой строке документа
        for index, line in enumerate(lines):
            line_lower = line.lower().replace("ё", "е")
            line_words = _WORD_RE.findall(line_lower)
            if not line_words:
                continue

            # Проверяем, есть ли фамилия в этой строке (с мягким порогом fuzzy)
            surname_matched = any(fuzz.ratio(target_surname, lw) >= 75 for lw in line_words)
            
            if surname_matched:
                # Если фамилия есть, проверяем, совпадают ли остальные слова (имя/отчество)
                score = float(fuzz.partial_ratio(query_lower, line_lower))
                
                # Если в запросе только фамилия или имя тоже частично сошлось
                if len(query_words) == 1 or score >= threshold:
                    heading = _find_heading(lines, index)
                    found_matches.append({
                        "line": line,
                        "heading": heading,
                        "score": score,
                    })

        # Убираем дубликаты строк
        seen_lines: set[str] = set()
        for match in found_matches:
            if match["line"] not in seen_lines:
                seen_lines.add(match["line"])
                results[query].append(match)

    return results
