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


def _extract_content(payload: dict[str, Any]) -> str:
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
    timeout: int = 90

    def request_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 3,
        temperature: float = 0.2,
    ) -> Any:
        url = _chat_completions_url(self.base_url)
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            request = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8", errors="ignore")
                data = json.loads(raw)
                return parse_json_response(_extract_content(data))
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
                if attempt == max_retries:
                    break
                time.sleep(min(2**attempt, 6))
        raise LLMError(f"模型调用失败：{last_error}") from last_error
