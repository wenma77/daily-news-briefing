from __future__ import annotations

import hashlib
import html
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return ensure_utc(parsedate_to_datetime(text))
    except (TypeError, ValueError, IndexError):
        pass
    try:
        normalized = text.replace("Z", "+00:00")
        return ensure_utc(datetime.fromisoformat(normalized))
    except ValueError:
        return None


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def truncate_text(text: str, limit: int) -> str:
    cleaned = normalize_space(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(limit - 1, 0)].rstrip() + "…"


def trim_complete_sentence(text: str, limit: int) -> str:
    cleaned = normalize_space(text).rstrip("…")
    if len(cleaned) <= limit:
        return cleaned
    trimmed = cleaned[:limit].rstrip()
    strong_punct = "。！？!?；;"
    strong_positions = [index for index, char in enumerate(trimmed) if char in strong_punct]
    if strong_positions:
        last = strong_positions[-1] + 1
        if last >= max(int(limit * 0.5), 12):
            return trimmed[:last].strip()
    soft_punct = "，,、"
    soft_positions = [index for index, char in enumerate(trimmed) if char in soft_punct]
    if soft_positions:
        last = soft_positions[-1]
        if last >= max(int(limit * 0.65), 18):
            return trimmed[:last].strip()
    return trimmed.rstrip("，,、;；:： ").strip()


def sha1_text(text: str, length: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self._parts.append(stripped)

    def text(self) -> str:
        return normalize_space(" ".join(self._parts))


def strip_html(text: str) -> str:
    unescaped = html.unescape(text or "")
    extractor = _HTMLTextExtractor()
    extractor.feed(unescaped)
    return extractor.text()


def remove_html_noise(html_text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg).*?>.*?</\1>", " ", html_text)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    return text


def safe_filename(text: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "-", text.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "preview"
