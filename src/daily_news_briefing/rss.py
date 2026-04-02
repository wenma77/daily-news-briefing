from __future__ import annotations

import ssl
import urllib.request
import xml.etree.ElementTree as ET
from typing import Iterable

from .models import ArticleCandidate, FeedSource
from .utils import parse_datetime, sha1_text, strip_html, truncate_text, utc_now

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


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

        items.append(
            ArticleCandidate(
                id=sha1_text(f"{source.name}|{link}|{title}"),
                title=strip_html(title),
                source=source.name,
                published_at=published_at,
                url=link.strip(),
                feed_summary=truncate_text(strip_html(summary), 800),
                category_hint=source.category_hint,
            )
        )
        if len(items) >= max_items:
            break
    return items


def fetch_feed_candidates(
    source: FeedSource,
    max_items: int,
    recency_hours: int,
) -> list[ArticleCandidate]:
    return parse_feed(
        fetch_text(source.url),
        source=source,
        max_items=max_items,
        recency_hours=recency_hours,
    )
