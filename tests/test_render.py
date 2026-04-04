from __future__ import annotations

import unittest
from datetime import UTC, datetime

import _path_setup  # noqa: F401

from daily_news_briefing.models import NewsletterDraft, NewsletterItem
from daily_news_briefing.render import render_html, render_text


class RenderTests(unittest.TestCase):
    def test_render_handles_long_titles(self) -> None:
        draft = NewsletterDraft(
            subject="测试日报",
            overview="今日重点主要集中在科技与国际局势。",
            lead_items=[
                NewsletterItem(
                    event_id="E1",
                    title="这是一个非常长但仍然应该正常显示且可点击查看原文的新闻标题，用来验证模板不会因为长度过大而渲染失败",
                    summary="这是一段较长的摘要，用来验证核心头条区域渲染正常。",
                    link="https://example.com/1",
                    category="科技",
                    source_name="Reuters",
                    domestic_reference_url="https://example.com/cn-1",
                    domestic_reference_name="第一财经",
                )
            ],
            brief_items=[
                NewsletterItem(
                    event_id="E2",
                    title="短标题",
                    summary="简要摘要。",
                    link="https://example.com/2",
                    category="国际",
                    source_name="界面新闻",
                )
            ],
            watch_items=["关注油价波动是否继续传导至全球风险资产。"],
            keywords=["科技", "国际"],
        )
        html = render_html(draft, datetime(2026, 4, 2, 0, 0, tzinfo=UTC))
        text = render_text(draft, datetime(2026, 4, 2, 0, 0, tzinfo=UTC))
        self.assertIn("原文链接", html)
        self.assertIn("国内参考", html)
        self.assertIn("今日主线", html)
        self.assertIn("今日重点", text)
        self.assertIn("短标题【界面新闻】", html)
        self.assertNotIn("为什么重要", html)
        self.assertIn("新闻速览", text)
        self.assertIn("北京时间", text)
        self.assertIn("今日关注点", html)
        self.assertIn("关注油价波动", text)
        self.assertIn("国内参考（第一财经）", text)
        self.assertNotIn("…", text)


if __name__ == "__main__":
    unittest.main()
