from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import ArticleCandidate
from .utils import normalize_space, sha1_text

TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_name",
    "utm_cid",
    "utm_reader",
    "gclid",
    "fbclid",
    "igshid",
    "spm",
    "from",
    "ref",
}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    normalized_path = parts.path.rstrip("/") or "/"
    normalized_query = urlencode(sorted(query_items))
    return urlunsplit(
        (
            parts.scheme.lower() or "https",
            parts.netloc.lower(),
            normalized_path,
            normalized_query,
            "",
        )
    )


def normalize_title(title: str) -> str:
    text = normalize_space(title).lower()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
    return normalize_space(text)


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(a=left, b=right).ratio()


def dedupe_candidates(
    candidates: list[ArticleCandidate],
    title_similarity: float,
) -> list[ArticleCandidate]:
    sorted_candidates = sorted(
        candidates,
        key=lambda item: (item.published_at, len(item.article_text), len(item.feed_summary)),
        reverse=True,
    )

    kept: list[ArticleCandidate] = []
    seen_urls: set[str] = set()
    normalized_titles: list[str] = []

    for candidate in sorted_candidates:
        norm_url = normalize_url(candidate.url)
        if norm_url in seen_urls:
            continue
        norm_title = normalize_title(candidate.title)
        if any(similarity(norm_title, other) >= title_similarity for other in normalized_titles):
            continue
        seen_urls.add(norm_url)
        normalized_titles.append(norm_title)
        candidate.url = norm_url
        kept.append(candidate)
    return kept


def build_fingerprint(title: str, category: str = "") -> str:
    base = f"{normalize_title(title)}|{normalize_title(category)}"
    return sha1_text(base, length=16)

