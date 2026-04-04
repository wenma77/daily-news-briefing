from __future__ import annotations

import io
import unittest
import urllib.error
from unittest.mock import patch

import _path_setup  # noqa: F401

from daily_news_briefing.llm import (
    OpenAICompatibleClient,
    _extract_responses_text,
    extract_json_block,
    parse_json_response,
)


class LLMParsingTests(unittest.TestCase):
    def test_extract_json_from_fenced_block(self) -> None:
        text = """```json
        {"kept_ids": ["a1", "a2"]}
        ```"""
        self.assertEqual(parse_json_response(text)["kept_ids"], ["a1", "a2"])

    def test_extract_json_from_mixed_text(self) -> None:
        text = '结果如下：{"subject":"日报"} 谢谢'
        self.assertIn('"subject":"日报"', extract_json_block(text))

    def test_extract_text_from_responses_payload(self) -> None:
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": '{"subject":"日报"}'}
                    ],
                }
            ]
        }
        self.assertEqual(_extract_responses_text(payload), '{"subject":"日报"}')

    def test_request_json_falls_back_to_chat_completions(self) -> None:
        client = OpenAICompatibleClient(
            base_url="https://example.com/v1",
            api_key="key",
            model="gpt-5.4",
            reasoning_effort="xhigh",
        )
        responses_error = urllib.error.HTTPError(
            url="https://example.com/v1/responses",
            code=404,
            msg="not found",
            hdrs=None,
            fp=io.BytesIO(b""),
        )

        with (
            patch.object(OpenAICompatibleClient, "_request_responses", side_effect=responses_error),
            patch.object(OpenAICompatibleClient, "_request_chat_completions", return_value='{"subject":"日报"}'),
        ):
            data = client.request_json("system", "user")
        self.assertEqual(data["subject"], "日报")


if __name__ == "__main__":
    unittest.main()
