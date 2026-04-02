from __future__ import annotations

import unittest

import _path_setup  # noqa: F401

from daily_news_briefing.models import FeedSource
from daily_news_briefing.rss import parse_feed


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Feed</title>
    <item>
      <title>央行宣布新的货币政策工具</title>
      <link>https://example.com/policy?utm_source=test</link>
      <description><![CDATA[<p>政策面出现重要变化。</p>]]></description>
      <pubDate>Wed, 02 Apr 2026 01:00:00 GMT</pubDate>
    </item>
    <item>
      <title>旧新闻</title>
      <link>https://example.com/old</link>
      <description>旧内容</description>
      <pubDate>Wed, 20 Mar 2024 01:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class RSSParserTests(unittest.TestCase):
    def test_parse_feed_keeps_recent_items(self) -> None:
        source = FeedSource(name="测试源", url="https://example.com/rss", category_hint="财经")
        items = parse_feed(SAMPLE_RSS, source=source, max_items=10, recency_hours=24 * 30)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "央行宣布新的货币政策工具")
        self.assertEqual(items[0].category_hint, "财经")
        self.assertIn("政策面出现重要变化", items[0].feed_summary)


if __name__ == "__main__":
    unittest.main()
