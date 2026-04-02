from __future__ import annotations

import unittest
from datetime import UTC, datetime

import _path_setup  # noqa: F401

from daily_news_briefing.dedupe import dedupe_candidates, normalize_url
from daily_news_briefing.models import ArticleCandidate


def _candidate(title: str, url: str) -> ArticleCandidate:
    return ArticleCandidate(
        id=title,
        title=title,
        source="测试源",
        published_at=datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
        url=url,
        feed_summary="摘要",
        category_hint="科技",
    )


class DedupeTests(unittest.TestCase):
    def test_normalize_url_removes_tracking(self) -> None:
        url = "https://example.com/a/?utm_source=x&id=1&fbclid=abc"
        self.assertEqual(normalize_url(url), "https://example.com/a?id=1")

    def test_dedupe_candidates_merges_similar_titles(self) -> None:
        items = [
            _candidate("苹果发布新芯片，瞄准 AI PC 市场", "https://example.com/a"),
            _candidate("苹果发布新芯片 瞄准 AI PC 市场", "https://example.com/b"),
        ]
        deduped = dedupe_candidates(items, title_similarity=0.88)
        self.assertEqual(len(deduped), 1)


if __name__ == "__main__":
    unittest.main()
