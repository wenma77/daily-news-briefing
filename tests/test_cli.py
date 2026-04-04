from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import _path_setup  # noqa: F401

from daily_news_briefing import cli
from daily_news_briefing.config import DedupeConfig, MailConfig, RuntimeEnv, ScheduleConfig, Settings, load_settings


class CLITests(unittest.TestCase):
    def _settings(self) -> Settings:
        return Settings(
            project_root=Path(_path_setup.ROOT),
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
                openai_reasoning_effort="xhigh",
                smtp_host="smtp.qq.com",
                smtp_port=465,
                smtp_user="sender@qq.com",
                smtp_pass="pass",
                mail_from="sender@qq.com",
                mail_to=["receiver@example.com"],
            ),
        )

    def test_build_parser_supports_expected_commands(self) -> None:
        parser = cli.build_parser()
        help_text = parser.format_help()
        self.assertIn("preview", help_text)
        self.assertIn("run", help_text)
        self.assertIn("send-test", help_text)

    def test_main_preview_passes_output_path(self) -> None:
        fake_pipeline = MagicMock()
        fake_pipeline.generate.return_value = MagicMock(
            draft=MagicMock(subject="测试日报", lead_items=[1], brief_items=[1], watch_items=[1]),
            html_body="<html></html>",
            text_body="预览",
            total_candidates=20,
            deduped_candidates=10,
            cleaned_candidates=8,
            grouped_events=7,
            curated_events=6,
            official_source_hits=2,
            items_with_domestic_reference=1,
            lead_family_counts={"policy": 1},
            source_zero_hits=["工信部新闻发布会"],
            google_news_primary_links=1,
            source_counts={"Reuters World": 3},
            health_warnings=[],
        )
        with (
            patch.object(cli, "load_settings", return_value=self._settings()),
            patch.object(cli, "NewsPipeline", return_value=fake_pipeline),
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.write_text", return_value=1),
            patch.object(sys, "argv", ["daily-news", "preview", "--output", "output/test.html"]),
        ):
            code = cli.main()
        self.assertEqual(code, 0)
        fake_pipeline.generate.assert_called_once_with()

    def test_main_send_test_calls_pipeline(self) -> None:
        fake_pipeline = MagicMock()
        with (
            patch.object(cli, "load_settings", return_value=self._settings()),
            patch.object(cli, "NewsPipeline", return_value=fake_pipeline),
            patch.object(sys, "argv", ["daily-news", "send-test"]),
        ):
            code = cli.main()
        self.assertEqual(code, 0)
        fake_pipeline.send_test.assert_called_once_with()

    def test_main_run_calls_pipeline(self) -> None:
        fake_pipeline = MagicMock()
        fake_pipeline.run.return_value = MagicMock(
            draft=MagicMock(subject="测试日报", lead_items=[1], brief_items=[1], watch_items=[1]),
            total_candidates=20,
            deduped_candidates=10,
            cleaned_candidates=8,
            grouped_events=8,
            curated_events=7,
            official_source_hits=2,
            items_with_domestic_reference=1,
            lead_family_counts={"policy": 1},
            source_zero_hits=["工信部新闻发布会"],
            google_news_primary_links=1,
            source_counts={"Reuters World": 3},
            health_warnings=[],
        )
        with (
            patch.object(cli, "load_settings", return_value=self._settings()),
            patch.object(cli, "NewsPipeline", return_value=fake_pipeline),
            patch.object(sys, "argv", ["daily-news", "run"]),
        ):
            code = cli.main()
        self.assertEqual(code, 0)
        fake_pipeline.run.assert_called_once_with()

    def test_summary_markdown_contains_key_stats(self) -> None:
        markdown = cli._summary_markdown_from_payload(
            {
                "subject": "测试日报",
                "total_candidates": 100,
                "deduped_candidates": 60,
                "cleaned_candidates": 40,
                "grouped_events": 12,
                "curated_events": 8,
                "lead_count": 6,
                "brief_count": 5,
                "watch_count": 3,
                "official_source_hits": 2,
                "items_with_domestic_reference": 1,
                "lead_family_counts": {"policy": 2},
                "source_zero_hits": ["工信部新闻发布会"],
                "google_news_primary_links": 1,
                "source_counts": {"Reuters World": 10, "商务部新闻发布": 3},
                "health_warnings": ["部分直连官方源今日未产出候选：工信部新闻发布会"],
            }
        )
        self.assertIn("Daily News Briefing Summary", markdown)
        self.assertIn("总候选数", markdown)
        self.assertIn("Reuters World", markdown)
        self.assertIn("工信部新闻发布会", markdown)
        self.assertIn("Google News 主链接数", markdown)

    def test_load_settings_reads_extended_source_fields(self) -> None:
        raw = """{
  "project_name": "测试项目",
  "schedule": {"cron": "0 8 * * *", "timezone": "Asia/Shanghai"},
  "recency_hours": 24,
  "max_candidates_per_source": 10,
  "max_candidates_for_llm": 10,
  "headline_count": 6,
  "brief_count": 6,
  "keyword_count": 5,
  "article_char_limit": 3000,
  "dedupe": {"title_similarity": 0.88, "event_similarity": 0.78},
  "mail": {"subject_template": "[{date}] 每日重点新闻简报"},
  "sources": [
    {
      "name": "商务部新闻发布",
      "url": "https://www.mofcom.gov.cn/xwfb/index.html",
      "category_hint": "国内",
      "fetcher": "html_list",
      "parser": "mofcom_press_index",
      "tier": "S",
      "role": "official"
    }
  ]
}"""
        with (
            patch("pathlib.Path.read_text", return_value=raw),
            patch("os.getenv", side_effect=lambda key, default="": default),
        ):
            settings = load_settings(Path(_path_setup.ROOT))
        self.assertEqual(settings.sources[0].fetcher, "html_list")
        self.assertEqual(settings.sources[0].parser, "mofcom_press_index")
        self.assertEqual(settings.sources[0].tier, "S")
        self.assertEqual(settings.sources[0].role, "official")
