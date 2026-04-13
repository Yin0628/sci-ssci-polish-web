"""Utilities for token counting and chunking while preserving paragraph boundaries."""

from __future__ import annotations

from typing import Any, Callable, Iterable, List

import tiktoken


def _get_encoding(model: str) -> tiktoken.Encoding:
    """Return a tokenizer encoding for the given model with a safe fallback."""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Estimate token count for a text string."""
    if not text:
        return 0
    encoding = _get_encoding(model)
    return len(encoding.encode(text))


def split_text_by_paragraphs(
    paragraphs: Iterable[str],
    max_tokens: int = 3000,
    model: str = "gpt-4o",
) -> List[List[str]]:
    """
    Split a list of paragraphs into token-bounded chunks.

    Paragraph boundaries are always preserved. If one paragraph exceeds the limit,
    it is emitted as a standalone chunk.
    """
    chunks: List[List[str]] = []
    current_chunk: List[str] = []
    current_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = count_tokens(paragraph, model=model)

        if current_chunk and current_tokens + paragraph_tokens > max_tokens:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(paragraph)
        current_tokens += paragraph_tokens

        if paragraph_tokens > max_tokens:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def split_items_by_tokens(
    items: Iterable[Any],
    text_getter: Callable[[Any], str],
    max_tokens: int = 3000,
    model: str = "gpt-4o",
) -> List[List[Any]]:
    """
    Split arbitrary items into chunks based on token count of each item text.

    Args:
        items: Sequence of item objects.
        text_getter: Function that returns the text content for each item.
        max_tokens: Token budget per chunk.
        model: Tokenizer model name.

    Returns:
        A list of item chunks.
    """
    chunks: List[List[Any]] = []
    current_chunk: List[Any] = []
    current_tokens = 0

    for item in items:
        text = text_getter(item)
        item_tokens = count_tokens(text, model=model)

        if current_chunk and current_tokens + item_tokens > max_tokens:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(item)
        current_tokens += item_tokens

        if item_tokens > max_tokens:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
