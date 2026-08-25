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


def _initials_score(query: str, line: str) -> float:
    query_words = _WORD_RE.findall(query.lower().replace("ё", "е"))
    line_words = _WORD_RE.findall(line.lower().replace("ё", "е"))
    if not query_words or not line_words:
        return 0.0

    surname_score = max(
        (fuzz.ratio(query_words[0], word) for word in line_words),
        default=0.0,
    )
    if surname_score < 75 or len(query_words) == 1:
        return surname_score

    try:
        surname_index = max(
            range(len(line_words)),
            key=lambda index: fuzz.ratio(query_words[0], line_words[index]),
        )
    except ValueError:
        return 0.0

    following_words = line_words[surname_index + 1 : surname_index + len(query_words)]
    if len(following_words) < len(query_words) - 1:
        return 0.0

    name_scores = [
        100.0
        if len(expected) == 1 and actual.startswith(expected)
        else float(fuzz.ratio(expected, actual))
        for expected, actual in zip(query_words[1:], following_words)
    ]
    return min([float(surname_score), *name_scores])


def _match_score(query: str, line: str, **_: Any) -> float:
    normalized_query = _normalize(query)
    normalized_line = _normalize(line)
    return max(
        float(fuzz.partial_ratio(normalized_query, normalized_line)),
        _initials_score(query, line),
    )


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
    threshold: int = 85,
) -> dict[str, list[SearchMatch]]:
    queries = parse_search_queries(surname)
    results: dict[str, list[SearchMatch]] = {query: [] for query in queries}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not queries:
        return results

    for query in queries:
        scored_lines = process.extract(
            query,
            lines,
            scorer=_match_score,
            score_cutoff=threshold,
            limit=None,
        )
        seen_lines: set[str] = set()
        for line, score, index in scored_lines:
            if score <= threshold or line in seen_lines:
                continue
            seen_lines.add(line)
            results[query].append(
                {
                    "line": line,
                    "heading": _find_heading(lines, index),
                    "score": float(score),
                }
            )

    return results
