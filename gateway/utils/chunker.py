from __future__ import annotations

from functools import lru_cache

import pysbd


@lru_cache(maxsize=8)
def _segmenter(language: str) -> pysbd.Segmenter:
    return pysbd.Segmenter(language=language, clean=True)


def chunk_text(text: str, max_chars: int, language: str) -> list[str]:
    if len(text) <= max_chars:
        return [text.strip()]

    segmenter = _segmenter(language)
    sentences = [sentence.strip() for sentence in segmenter.segment(text) if sentence.strip()]

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence_parts = _split_long_sentence(sentence, max_chars)
        for part in sentence_parts:
            if not current:
                current = part
                continue

            candidate = f"{current} {part}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                chunks.append(current)
                current = part

    if current:
        chunks.append(current)

    return chunks


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]

    words = sentence.split()
    if not words:
        return [sentence[i : i + max_chars] for i in range(0, len(sentence), max_chars)]

    parts: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.extend([word[i : i + max_chars] for i in range(0, len(word), max_chars)])
            continue

        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            parts.append(current)
            current = word

    if current:
        parts.append(current)

    return parts

