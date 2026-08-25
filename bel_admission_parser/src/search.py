from __future__ import annotations

import re

from rapidfuzz import process

_QUERY_SEPARATOR = re.compile(r"\s*(?:,|\n|\s+и\s+)\s*", re.IGNORECASE)


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def parse_search_queries(surnames: str | list[str]) -> list[str]:
    raw_values = [surnames] if isinstance(surnames, str) else surnames
    queries: list[str] = []
    seen: set[str] = set()

    for value in raw_values:
        if not isinstance(value, str):
            continue
        for part in _QUERY_SEPARATOR.split(value):
            query = " ".join(part.split())
            normalized_query = _normalize(query)
            if normalized_query and normalized_query not in seen:
                seen.add(normalized_query)
                queries.append(query)

    return queries


def search_surname(
    text: str,
    surname: str | list[str],
    threshold: int = 85,
) -> dict[str, list[str]]:
    queries = parse_search_queries(surname)
    results: dict[str, list[str]] = {query: [] for query in queries}
    if not text or not queries:
        return results

    original_lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized_lines = [_normalize(line) for line in original_lines]

    for query in queries:
        matches = process.extract(
            _normalize(query),
            normalized_lines,
            score_cutoff=threshold,
            limit=None,
        )
        results[query] = list(
            dict.fromkeys(
                original_lines[index]
                for _, score, index in matches
                if score > threshold
            )
        )

    return results
