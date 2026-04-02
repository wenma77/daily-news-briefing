from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from email import message_from_string
from email.header import decode_header
from pathlib import Path
from unittest.mock import patch

import _path_setup

from daily_news_briefing.config import DedupeConfig, MailConfig, RuntimeEnv, ScheduleConfig, Settings
from daily_news_briefing.models import ArticleCandidate, EventCard, NewsletterDraft, NewsletterItem
from daily_news_briefing.editor import AINewsEditor
from daily_news_briefing.pipeline import NewsPipeline


def _decode_mime_header(value: str) -> str:
    parts: list[str] = []
    for chunk, encoding in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(encoding or "utf-8", errors="ignore"))
        else:
            parts.append(chunk)
    return "".join(parts)


def _settings(project_root: Path) -> Settings:
    return Settings(
        project_root=project_root,
        project_name="测试项目",
        schedule=ScheduleConfig(cron="0 8 * * *", timezone="Asia/Shanghai"),
        recency_hours=24,
        max_candidates_per_source=10,
        max_candidates_for_llm=10,
        headline_count=6,
        brief_count=6,
        keyword_count=5,
        article_char_limit=3000,
        dedupe=DedupeConfig(title_similarity=0.88, event_similarity=0.78),
        mail=MailConfig(subject_template="[{date}] 每日重点新闻简报"),
        sources=[],
        runtime=RuntimeEnv(
            openai_base_url="https://example.com/v1",
            openai_api_key="test-key",
            openai_model="test-model",
            smtp_host="smtp.qq.com",
            smtp_port=465,
            smtp_user="sender@qq.com",
            smtp_pass="pass",
            mail_from="sender@qq.com",
            mail_to=["receiver@example.com"],
        ),
    )


class PipelineIntegrationTests(unittest.TestCase):
    def test_preview_generates_html_and_txt(self) -> None:
        root = _path_setup.ROOT
        settings = _settings(root)
        pipeline = NewsPipeline(settings)

        candidates = [
            ArticleCandidate(
                id="a1",
                title="央行公布重要政策",
                source="测试源",
                published_at=datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
                url="https://example.com/a1",
                feed_summary="政策面出现变化",
                category_hint="财经",
                article_text="政策面出现变化，影响金融市场预期。",
                article_text_source="article",
            )
        ]
        events = [
            EventCard(
                event_id="E1",
                title="央行公布重要政策",
                category="财经",
                importance_score=90,
                why_it_matters="会影响市场预期和流动性判断。",
                summary="央行发布新的政策工具安排，市场关注后续影响。",
                article_ids=["a1"],
                representative_url="https://example.com/a1",
                fingerprint="fp1",
            )
        ]
        draft = NewsletterDraft(
            subject="[2026-04-02] 每日重点新闻简报",
            overview="今天的重要新闻主要集中在财经领域。",
            lead_items=[
                NewsletterItem(
                    event_id="E1",
                    title="央行公布重要政策",
                    summary="央行发布新的政策工具安排，市场关注后续影响。",
                    why_important="会影响市场预期和流动性判断。",
                    link="https://example.com/a1",
                    category="财经",
                )
            ],
            brief_items=[],
            keywords=["财经"],
        )

        output_path = root / "preview-test.html"
        with (
            patch.object(NewsPipeline, "_collect_candidates", return_value=candidates),
            patch.object(AINewsEditor, "clean_candidates", return_value=candidates),
            patch.object(AINewsEditor, "group_events", return_value=events),
            patch.object(AINewsEditor, "draft_newsletter", return_value=draft),
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch("pathlib.Path.write_text", return_value=1) as mock_write_text,
        ):
            final_path = pipeline.preview(output_path=output_path)

        self.assertEqual(final_path, output_path)
        mock_mkdir.assert_called()
        written_paths = [str(call.args[0]) for call in mock_write_text.call_args_list]
        self.assertIn("<html", written_paths[0])
        self.assertTrue(any("今日重点新闻" in text or "每日重点新闻" in text for text in written_paths))
        self.assertEqual(len(mock_write_text.call_args_list), 2)

    def test_send_test_uses_html_and_plain_bodies(self) -> None:
        settings = _settings(_path_setup.ROOT)
        pipeline = NewsPipeline(settings)

        with patch("daily_news_briefing.mailer.smtplib.SMTP_SSL") as smtp_ssl:
            server = smtp_ssl.return_value.__enter__.return_value
            pipeline.send_test()

        server.login.assert_called_once_with("sender@qq.com", "pass")
        send_args = server.sendmail.call_args.args
        message = message_from_string(send_args[2])
        self.assertEqual(send_args[0], "sender@qq.com")
        self.assertEqual(send_args[1], ["receiver@example.com"])
        self.assertEqual(_decode_mime_header(message["Subject"]), "测试邮件：每日重点新闻简报")
        self.assertIn("Content-Type: text/html", send_args[2])
        self.assertIn("Content-Type: text/plain", send_args[2])


if __name__ == "__main__":
    unittest.main()
