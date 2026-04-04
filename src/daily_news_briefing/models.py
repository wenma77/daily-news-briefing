from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class FeedSource:
    name: str
    url: str
    category_hint: str
    fetcher: str = "rss"
    parser: str = ""
    tier: str = "A"
    role: str = "discovery"


@dataclass(slots=True)
class ArticleCandidate:
    id: str
    title: str
    source: str
    publisher: str
    published_at: datetime
    url: str
    feed_summary: str
    category_hint: str
    article_text: str = ""
    article_text_source: str = "feed"

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "publisher": self.publisher,
            "published_at": self.published_at.isoformat(),
            "url": self.url,
            "feed_summary": self.feed_summary,
            "category_hint": self.category_hint,
            "article_text": self.article_text,
            "article_text_source": self.article_text_source,
        }


@dataclass(slots=True)
class EventCard:
    event_id: str
    title: str
    category: str
    importance_score: int
    summary: str
    article_ids: list[str]
    representative_url: str
    source_name: str
    domestic_reference_url: str = ""
    domestic_reference_name: str = ""
    why_it_matters: str = ""
    fingerprint: str = ""

    def to_prompt_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NewsletterItem:
    event_id: str
    title: str
    summary: str
    link: str
    category: str
    source_name: str
    domestic_reference_url: str = ""
    domestic_reference_name: str = ""
    why_important: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NewsletterDraft:
    subject: str
    overview: str
    lead_items: list[NewsletterItem] = field(default_factory=list)
    brief_items: list[NewsletterItem] = field(default_factory=list)
    watch_items: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "overview": self.overview,
            "lead_items": [item.to_dict() for item in self.lead_items],
            "brief_items": [item.to_dict() for item in self.brief_items],
            "watch_items": self.watch_items,
            "keywords": self.keywords,
        }


@dataclass(slots=True)
class SeenEvent:
    fingerprint: str
    title: str
    sent_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "title": self.title,
            "sent_at": self.sent_at.isoformat(),
        }
