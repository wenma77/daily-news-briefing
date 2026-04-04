from __future__ import annotations

import html
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Callable, Iterable
from urllib.parse import urljoin

from .models import ArticleCandidate, FeedSource
from .utils import parse_datetime, sha1_text, strip_html, truncate_text, utc_now

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

ANCHOR_RE = re.compile(
    r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<title>.*?)</a>",
    flags=re.I | re.S,
)
DATE_RE = re.compile(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)")
HTML_SKIP_TITLES = {
    "首页",
    "更多",
    "进入频道",
    "返回顶部",
    "政务公开",
    "新闻发布会",
    "新闻发布",
    "政务服务",
    "互动交流",
}
PBC_TITLE_KEYWORDS = {
    "货币政策",
    "公开市场",
    "贷款市场报价利率",
    "金融统计",
    "社会融资",
    "MLF",
    "逆回购",
    "利率",
    "数字人民币",
    "支付体系",
    "金融稳定",
    "答记者问",
    "科技金融",
    "例会",
}

PBC_SKIP_TITLE_KEYWORDS = {
    "机关服务中心",
    "党校",
    "纪念币",
    "工会",
    "离退休",
    "后勤",
    "采购",
    "物业",
}


def _extract_title_and_publisher(raw_title: str, fallback_publisher: str) -> tuple[str, str]:
    title = strip_html(raw_title).strip()
    publisher = fallback_publisher.strip()

    bracket_match = re.search(r"^(.*?)[\s　]*【([^】]{1,30})】$", title)
    if bracket_match:
        title = bracket_match.group(1).strip()
        publisher = bracket_match.group(2).strip()

    dash_match = re.search(r"^(.*?)[\s　]*-\s*([^-\s][^-]{0,30})$", title)
    if dash_match:
        title = dash_match.group(1).strip()
        publisher = dash_match.group(2).strip()

    title = re.sub(r"[_\s]*手机新浪网$", "", title)
    title = re.sub(r"\|[^|]{0,20}(?:\|[^|]{0,20}){1,}$", "", title).strip()
    title = re.sub(r"\s{2,}", " ", title).strip(" -|_")
    return title or strip_html(raw_title).strip(), publisher or fallback_publisher


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return response.read().decode("utf-8", errors="ignore")


def _child_text(element: ET.Element, paths: Iterable[str]) -> str:
    for path in paths:
        child = element.find(path)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def parse_feed(
    xml_text: str,
    source: FeedSource,
    max_items: int,
    recency_hours: int,
) -> list[ArticleCandidate]:
    root = ET.fromstring(xml_text)
    now = utc_now()
    cutoff = now.timestamp() - (recency_hours * 3600)
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }

    item_nodes = root.findall(".//item")
    is_atom = False
    if not item_nodes:
        item_nodes = root.findall(".//atom:entry", namespaces)
        is_atom = True

    items: list[ArticleCandidate] = []
    for node in item_nodes[: max_items * 2]:
        title = _child_text(node, ["title", "atom:title"])
        summary = _child_text(
            node,
            ["description", "summary", "content:encoded", "atom:summary"],
        )
        pub_raw = _child_text(
            node,
            ["pubDate", "published", "updated", "atom:published", "atom:updated"],
        )
        link = ""
        if is_atom:
            for link_node in node.findall("atom:link", namespaces):
                href = link_node.attrib.get("href", "").strip()
                rel = link_node.attrib.get("rel", "alternate").strip()
                if href and rel in {"alternate", ""}:
                    link = href
                    break
        else:
            link = _child_text(node, ["link"])

        published_at = parse_datetime(pub_raw) or now
        if published_at.timestamp() < cutoff:
            continue
        if not title or not link:
            continue

        clean_title, publisher = _extract_title_and_publisher(title, source.name)
        items.append(
            ArticleCandidate(
                id=sha1_text(f"{source.name}|{link}|{title}"),
                title=clean_title,
                source=source.name,
                publisher=publisher,
                published_at=published_at,
                url=link.strip(),
                feed_summary=truncate_text(strip_html(summary), 800),
                category_hint=source.category_hint,
            )
        )
        if len(items) >= max_items:
            break
    return items


def parse_html_list(
    html_text: str,
    source: FeedSource,
    max_items: int,
    recency_hours: int,
) -> list[ArticleCandidate]:
    parser_key = source.parser.strip()
    if not parser_key:
        return []
    parser = HTML_LIST_PARSERS.get(parser_key)
    if parser is None:
        return []
    return parser(html_text, source, max_items, recency_hours)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", strip_html(html.unescape(text))).strip()


def _normalize_date_text(date_text: str) -> str:
    if not date_text:
        return ""
    raw = date_text.strip()
    raw = raw.replace("年", "-").replace("月", "-").replace("日", "")
    raw = raw.replace("/", "-").replace(".", "-")
    match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", raw)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _extract_anchor_entries(html_text: str, base_url: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for match in ANCHOR_RE.finditer(html_text):
        href = html.unescape(match.group("href")).strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        title = _normalize_text(match.group("title"))
        if not title or title in HTML_SKIP_TITLES or len(title) < 4:
            continue
        context = strip_html(html_text[max(0, match.start() - 120) : match.end() + 180])
        date_match = DATE_RE.search(context)
        entries.append(
            {
                "title": title,
                "url": urljoin(base_url, href),
                "date_text": _normalize_date_text(date_match.group(1) if date_match else ""),
            }
        )
    return entries


def _build_html_candidates(
    entries: list[dict[str, str]],
    source: FeedSource,
    max_items: int,
    recency_hours: int,
    *,
    require_date: bool,
) -> list[ArticleCandidate]:
    now = utc_now()
    cutoff = now.timestamp() - (recency_hours * 3600)
    items: list[ArticleCandidate] = []
    seen_urls: set[str] = set()
    for entry in entries:
        title = entry["title"]
        url = entry["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        published_at = parse_datetime(entry["date_text"]) if entry["date_text"] else None
        if require_date and published_at is None:
            continue
        if published_at is not None and published_at.timestamp() < cutoff:
            continue
        items.append(
            ArticleCandidate(
                id=sha1_text(f"{source.name}|{url}|{title}"),
                title=title,
                source=source.name,
                publisher=source.name,
                published_at=published_at or now,
                url=url,
                feed_summary="",
                category_hint=source.category_hint,
            )
        )
        if len(items) >= max_items:
            break
    return items


def _parse_mofcom_press_index(
    html_text: str,
    source: FeedSource,
    max_items: int,
    recency_hours: int,
) -> list[ArticleCandidate]:
    entries = [
        entry
        for entry in _extract_anchor_entries(html_text, source.url)
        if entry["date_text"] and len(entry["title"]) >= 8
    ]
    return _build_html_candidates(entries, source, max_items, recency_hours, require_date=True)


def _parse_miit_press_index(
    html_text: str,
    source: FeedSource,
    max_items: int,
    recency_hours: int,
) -> list[ArticleCandidate]:
    entries = [
        entry
        for entry in _extract_anchor_entries(html_text, source.url)
        if entry["date_text"] and len(entry["title"]) >= 8
    ]
    return _build_html_candidates(entries, source, max_items, recency_hours, require_date=True)


def _parse_pbc_home_updates(
    html_text: str,
    source: FeedSource,
    max_items: int,
    recency_hours: int,
) -> list[ArticleCandidate]:
    entries = []
    for entry in _extract_anchor_entries(html_text, source.url):
        title = entry["title"]
        if len(title) < 8:
            continue
        if any(keyword in title for keyword in PBC_SKIP_TITLE_KEYWORDS):
            continue
        if not any(keyword in title for keyword in PBC_TITLE_KEYWORDS):
            continue
        entries.append(entry)
    return _build_html_candidates(entries, source, max_items, recency_hours, require_date=False)


HTML_LIST_PARSERS: dict[str, Callable[[str, FeedSource, int, int], list[ArticleCandidate]]] = {
    "mofcom_press_index": _parse_mofcom_press_index,
    "miit_press_index": _parse_miit_press_index,
    "pbc_home_updates": _parse_pbc_home_updates,
}


def fetch_feed_candidates(
    source: FeedSource,
    max_items: int,
    recency_hours: int,
) -> list[ArticleCandidate]:
    content = fetch_text(source.url)
    fetcher = source.fetcher.strip().lower()
    if fetcher == "html_list":
        return parse_html_list(
            content,
            source=source,
            max_items=max_items,
            recency_hours=recency_hours,
        )
    if fetcher not in {"rss", "google_news"}:
        return []
    return parse_feed(
        content,
        source=source,
        max_items=max_items,
        recency_hours=recency_hours,
    )
