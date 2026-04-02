from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import _path_setup  # noqa: F401

from daily_news_briefing import cli


class CLITests(unittest.TestCase):
    def test_build_parser_supports_expected_commands(self) -> None:
        parser = cli.build_parser()
        help_text = parser.format_help()
        self.assertIn("preview", help_text)
        self.assertIn("run", help_text)
        self.assertIn("send-test", help_text)

    def test_main_preview_passes_output_path(self) -> None:
        fake_pipeline = MagicMock()
        fake_pipeline.preview.return_value = Path("output/test.html")
        with (
            patch.object(cli, "load_settings", return_value=object()),
            patch.object(cli, "NewsPipeline", return_value=fake_pipeline),
            patch.object(sys, "argv", ["daily-news", "preview", "--output", "output/test.html"]),
        ):
            code = cli.main()
        self.assertEqual(code, 0)
        fake_pipeline.preview.assert_called_once()
        self.assertEqual(fake_pipeline.preview.call_args.kwargs["output_path"], Path("output/test.html"))

    def test_main_send_test_calls_pipeline(self) -> None:
        fake_pipeline = MagicMock()
        with (
            patch.object(cli, "load_settings", return_value=object()),
            patch.object(cli, "NewsPipeline", return_value=fake_pipeline),
            patch.object(sys, "argv", ["daily-news", "send-test"]),
        ):
            code = cli.main()
        self.assertEqual(code, 0)
        fake_pipeline.send_test.assert_called_once_with()

    def test_main_run_calls_pipeline(self) -> None:
        fake_pipeline = MagicMock()
        fake_pipeline.run.return_value = MagicMock(
            draft=MagicMock(subject="测试日报", lead_items=[1], brief_items=[1]),
            total_candidates=20,
            deduped_candidates=10,
            grouped_events=8,
        )
        with (
            patch.object(cli, "load_settings", return_value=object()),
            patch.object(cli, "NewsPipeline", return_value=fake_pipeline),
            patch.object(sys, "argv", ["daily-news", "run"]),
        ):
            code = cli.main()
        self.assertEqual(code, 0)
        fake_pipeline.run.assert_called_once_with()
