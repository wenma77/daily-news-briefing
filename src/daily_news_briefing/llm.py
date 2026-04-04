from __future__ import annotations

import json
import re
import time
from http.client import RemoteDisconnected
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class LLMError(RuntimeError):
    pass


def _responses_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/responses"):
        return base
    if base.endswith("/v1"):
        return f"{base}/responses"
    return f"{base}/v1/responses"


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def extract_json_block(text: str) -> str:
    cleaned = text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", cleaned, flags=re.S)
    if fenced_match:
        return fenced_match.group(1)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end != -1 and end > start:
            return cleaned[start : end + 1]
    return cleaned


def parse_json_response(text: str) -> Any:
    return json.loads(extract_json_block(text))


def _extract_responses_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    outputs = payload.get("output", [])
    parts: list[str] = []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        if output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            content_type = content.get("type")
            if content_type in {"output_text", "text"}:
                parts.append(str(content.get("text", "")))
    text = "\n".join(part for part in parts if part).strip()
    if text:
        return text
    raise LLMError("Responses API 返回中缺少可解析文本。")


def _extract_chat_completions_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        raise LLMError("模型返回中缺少 choices。")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts).strip()
    raise LLMError("模型返回格式无法识别。")


@dataclass(slots=True)
class OpenAICompatibleClient:
    base_url: str
    api_key: str
    model: str
    reasoning_effort: str = "xhigh"
    timeout: int = 180

    def request_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 3,
        temperature: float = 0.2,
    ) -> Any:
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                text = self._request_responses(system_prompt, user_prompt)
                return parse_json_response(text)
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                json.JSONDecodeError,
                LLMError,
                RemoteDisconnected,
                ConnectionError,
                OSError,
            ) as exc:
                last_error = exc
                responses_should_fallback = isinstance(exc, urllib.error.HTTPError) and exc.code in {400, 404, 405, 422}
                if responses_should_fallback:
                    try:
                        text = self._request_chat_completions(system_prompt, user_prompt, temperature=temperature)
                        return parse_json_response(text)
                    except (
                        urllib.error.HTTPError,
                        urllib.error.URLError,
                        TimeoutError,
                        json.JSONDecodeError,
                        LLMError,
                        RemoteDisconnected,
                        ConnectionError,
                        OSError,
                    ) as fallback_exc:
                        last_error = fallback_exc
                if attempt == max_retries:
                    break
                time.sleep(min(2**attempt, 6))
        raise LLMError(f"模型调用失败：{last_error}") from last_error

    def _request_responses(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "reasoning": {"effort": self.reasoning_effort},
            "text": {"format": {"type": "text"}},
        }
        data = self._post_json(_responses_url(self.base_url), payload)
        return _extract_responses_text(data)

    def _request_chat_completions(self, system_prompt: str, user_prompt: str, *, temperature: float) -> str:
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        data = self._post_json(_chat_completions_url(self.base_url), payload)
        return _extract_chat_completions_text(data)

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8", errors="ignore")
        return json.loads(raw)
