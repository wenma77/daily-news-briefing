from __future__ import annotations

import base64
import unittest
from unittest.mock import patch

import _path_setup  # noqa: F401

from daily_news_briefing.article import resolve_google_news_url
from daily_news_briefing.models import FeedSource
from daily_news_briefing.rss import fetch_feed_candidates, parse_feed, parse_html_list


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

SAMPLE_MOFCOM_HTML = """
<html><body>
<ul>
  <li><a href="/xwfb/xwfyrth/art/2026/art_1.html">商务部回应中美经贸问题</a><span>2026-04-02</span></li>
  <li><a href="/xwfb/xwfyrth/art/2026/art_2.html">商务部介绍广交会筹备情况</a><span>2026-04-01</span></li>
</ul>
</body></html>
"""

SAMPLE_MIIT_HTML = """
<html><body>
<div class="list">
  <a href="/xwfb/xwfbh/art/2026/art_1.html">工业和信息化部召开新闻发布会介绍工业经济运行情况</a>
  <span>2026-04-02</span>
  <a href="/xwfb/xwfbh/art/2026/art_2.html">工业和信息化部答记者问：推动算力基础设施建设</a>
  <span>2026-04-01</span>
</div>
</body></html>
"""

SAMPLE_PBC_HTML = """
<html><body>
<div class="content">
  <a href="/goutongjiaoliu/113456/113469/5702453/index.html">中国人民银行召开货币政策执行情况新闻发布会</a>
  <a href="/diaochatongji/tongjishuju/202604/t20260402_123.html">2026年3月金融统计数据报告</a>
  <a href="/rmyh/renhangdangxiao/test.html">中国人民银行机关服务中心</a>
</div>
</body></html>
"""


class RSSParserTests(unittest.TestCase):
    def test_parse_feed_keeps_recent_items(self) -> None:
        source = FeedSource(name="测试源", url="https://example.com/rss", category_hint="财经")
        items = parse_feed(SAMPLE_RSS, source=source, max_items=10, recency_hours=24 * 30)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "央行宣布新的货币政策工具")
        self.assertEqual(items[0].category_hint, "财经")
        self.assertIn("政策面出现重要变化", items[0].feed_summary)

    def test_parse_feed_extracts_publisher_from_title(self) -> None:
        source = FeedSource(name="Google News 国际大公司", url="https://example.com/rss", category_hint="科技")
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Feed</title>
    <item>
      <title>OpenAI 发布新模型 - Reuters</title>
      <link>https://example.com/openai</link>
      <description>新模型发布。</description>
      <pubDate>Wed, 02 Apr 2026 01:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""
        items = parse_feed(xml, source=source, max_items=10, recency_hours=24 * 30)
        self.assertEqual(items[0].title, "OpenAI 发布新模型")
        self.assertEqual(items[0].publisher, "Reuters")

    def test_resolve_google_news_url_decodes_direct_token(self) -> None:
        resolve_google_news_url.cache_clear()
        original = "https://example.com/article/123"
        payload = b"\x08\x13\x22" + bytes([len(original)]) + original.encode("utf-8") + b"\xd2\x01\x00"
        token = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        url = f"https://news.google.com/rss/articles/{token}"
        self.assertEqual(resolve_google_news_url(url), original)

    def test_resolve_google_news_url_decodes_au_yql_via_batch(self) -> None:
        resolve_google_news_url.cache_clear()
        url = "https://news.google.com/rss/articles/CBMijwFBVV95cUxNMGxOTG9qblBLTEU3TkNWWDF2dV9mbVIxZTY0S290cllGekM1RjIxcmVqLUVfb0ZEdlJ1aURRRjhFcnhKNFNRelpvWHRJTlJRcXRuWVJva2hMbG54M3UyUUtOLWtoVEZ5R2pUN1VSVEp5TEg2N0J1RUdkMHVvNVpGNzZna3VfU3Z2cm5ieElUdw"
        with (
            patch("daily_news_briefing.article._decode_google_news_binary_url", return_value="AU_yqLmocktoken"),
            patch("daily_news_briefing.article._fetch_google_news_metadata", return_value=("1775293206", "sig")),
            patch(
                "daily_news_briefing.article._fetch_google_news_decoded_url",
                return_value="https://www.21jingji.com/article/test.html",
            ),
        ):
            self.assertEqual(resolve_google_news_url(url), "https://www.21jingji.com/article/test.html")

    def test_parse_html_list_for_mofcom(self) -> None:
        source = FeedSource(
            name="商务部新闻发布",
            url="https://www.mofcom.gov.cn/xwfb/index.html",
            category_hint="国内",
            fetcher="html_list",
            parser="mofcom_press_index",
            tier="S",
            role="official",
        )
        items = parse_html_list(SAMPLE_MOFCOM_HTML, source=source, max_items=10, recency_hours=24 * 30)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "商务部回应中美经贸问题")
        self.assertEqual(items[0].publisher, "商务部新闻发布")
        self.assertTrue(items[0].url.startswith("https://www.mofcom.gov.cn/"))

    def test_parse_html_list_for_miit(self) -> None:
        source = FeedSource(
            name="工信部新闻发布会",
            url="https://wap.miit.gov.cn/xwfb/xwfbh/index.html",
            category_hint="科技",
            fetcher="html_list",
            parser="miit_press_index",
            tier="S",
            role="official",
        )
        items = parse_html_list(SAMPLE_MIIT_HTML, source=source, max_items=10, recency_hours=24 * 30)
        self.assertEqual(len(items), 2)
        self.assertIn("工业和信息化部召开新闻发布会", items[0].title)

    def test_parse_html_list_for_pbc(self) -> None:
        source = FeedSource(
            name="中国人民银行首页公开信息",
            url="https://www.pbc.gov.cn/rmyh/index.html",
            category_hint="财经",
            fetcher="html_list",
            parser="pbc_home_updates",
            tier="S",
            role="official",
        )
        items = parse_html_list(SAMPLE_PBC_HTML, source=source, max_items=10, recency_hours=24 * 30)
        self.assertEqual(len(items), 2)
        self.assertIn("货币政策", items[0].title)

    def test_fetch_feed_candidates_dispatches_by_fetcher(self) -> None:
        source = FeedSource(
            name="商务部新闻发布",
            url="https://www.mofcom.gov.cn/xwfb/index.html",
            category_hint="国内",
            fetcher="html_list",
            parser="mofcom_press_index",
            tier="S",
            role="official",
        )
        with patch("daily_news_briefing.rss.fetch_text", return_value=SAMPLE_MOFCOM_HTML):
            items = fetch_feed_candidates(source, max_items=10, recency_hours=24 * 30)
        self.assertEqual(len(items), 2)

    def test_parse_html_list_without_parser_returns_empty(self) -> None:
        source = FeedSource(
            name="商务部新闻发布",
            url="https://www.mofcom.gov.cn/xwfb/index.html",
            category_hint="国内",
            fetcher="html_list",
        )
        items = parse_html_list(SAMPLE_MOFCOM_HTML, source=source, max_items=10, recency_hours=24 * 30)
        self.assertEqual(items, [])

    def test_unknown_fetcher_returns_empty(self) -> None:
        source = FeedSource(
            name="未知来源",
            url="https://example.com/any",
            category_hint="国内",
            fetcher="unknown",
        )
        with patch("daily_news_briefing.rss.fetch_text", return_value=SAMPLE_RSS):
            items = fetch_feed_candidates(source, max_items=10, recency_hours=24 * 30)
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
