from __future__ import annotations

import re
import ssl
import urllib.request

from .utils import remove_html_noise, strip_html, truncate_text

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def _extract_candidate_block(html_text: str) -> str:
    patterns = [
        r"(?is)<article\b[^>]*>(.*?)</article>",
        r"(?is)<main\b[^>]*>(.*?)</main>",
        r"(?is)<body\b[^>]*>(.*?)</body>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text)
        if match:
            return match.group(1)
    return html_text


def _clean_lines(text: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in re.split(r"[\r\n]+", text):
        line = raw_line.strip()
        if len(line) < 20:
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return " ".join(lines)


def fetch_article_text(url: str, char_limit: int, timeout: int = 15) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read().decode("utf-8", errors="ignore")

    if "html" not in content_type.lower() and "<html" not in raw.lower():
        return "", "feed"

    candidate_block = _extract_candidate_block(remove_html_noise(raw))
    text = _clean_lines(strip_html(candidate_block))
    return truncate_text(text, char_limit), "article" if text else "feed"

