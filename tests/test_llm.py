from __future__ import annotations

import unittest

import _path_setup  # noqa: F401

from daily_news_briefing.llm import extract_json_block, parse_json_response


class LLMParsingTests(unittest.TestCase):
    def test_extract_json_from_fenced_block(self) -> None:
        text = """```json
        {"kept_ids": ["a1", "a2"]}
        ```"""
        self.assertEqual(parse_json_response(text)["kept_ids"], ["a1", "a2"])

    def test_extract_json_from_mixed_text(self) -> None:
        text = '结果如下：{"subject":"日报"} 谢谢'
        self.assertIn('"subject":"日报"', extract_json_block(text))


if __name__ == "__main__":
    unittest.main()
