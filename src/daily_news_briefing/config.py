from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .models import FeedSource


@dataclass(slots=True)
class ScheduleConfig:
    cron: str
    timezone: str


@dataclass(slots=True)
class DedupeConfig:
    title_similarity: float
    event_similarity: float


@dataclass(slots=True)
class MailConfig:
    subject_template: str


@dataclass(slots=True)
class RuntimeEnv:
    openai_base_url: str
    openai_api_key: str
    openai_model: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    mail_from: str
    mail_to: list[str]

    def missing_ai(self) -> list[str]:
        missing: list[str] = []
        if not self.openai_base_url:
            missing.append("OPENAI_BASE_URL")
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.openai_model:
            missing.append("OPENAI_MODEL")
        return missing

    def missing_mail(self) -> list[str]:
        missing: list[str] = []
        if not self.smtp_host:
            missing.append("SMTP_HOST")
        if not self.smtp_port:
            missing.append("SMTP_PORT")
        if not self.smtp_user:
            missing.append("SMTP_USER")
        if not self.smtp_pass:
            missing.append("SMTP_PASS")
        if not self.mail_from:
            missing.append("MAIL_FROM")
        if not self.mail_to:
            missing.append("MAIL_TO")
        return missing


@dataclass(slots=True)
class Settings:
    project_root: Path
    project_name: str
    schedule: ScheduleConfig
    recency_hours: int
    max_candidates_per_source: int
    max_candidates_for_llm: int
    headline_count: int
    brief_count: int
    keyword_count: int
    article_char_limit: int
    dedupe: DedupeConfig
    mail: MailConfig
    sources: list[FeedSource]
    runtime: RuntimeEnv

    @property
    def state_file(self) -> Path:
        return self.project_root / "state" / "seen_events.json"

    @property
    def output_dir(self) -> Path:
        return self.project_root / "output"


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_mail_to(raw: str) -> list[str]:
    separators = raw.replace(";", ",")
    return [item.strip() for item in separators.split(",") if item.strip()]


def load_settings(project_root: Path | None = None) -> Settings:
    root = project_root or _default_project_root()
    raw = json.loads((root / "config.yaml").read_text(encoding="utf-8"))

    runtime = RuntimeEnv(
        openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "").strip(),
        smtp_host=os.getenv("SMTP_HOST", "smtp.qq.com").strip(),
        smtp_port=int(os.getenv("SMTP_PORT", "465").strip() or "465"),
        smtp_user=os.getenv("SMTP_USER", "").strip(),
        smtp_pass=os.getenv("SMTP_PASS", "").strip(),
        mail_from=os.getenv("MAIL_FROM", "").strip(),
        mail_to=_parse_mail_to(os.getenv("MAIL_TO", "").strip()),
    )

    sources = [
        FeedSource(
            name=item["name"],
            url=item["url"],
            category_hint=item["category_hint"],
        )
        for item in raw["sources"]
    ]

    return Settings(
        project_root=root,
        project_name=raw["project_name"],
        schedule=ScheduleConfig(**raw["schedule"]),
        recency_hours=int(raw["recency_hours"]),
        max_candidates_per_source=int(raw["max_candidates_per_source"]),
        max_candidates_for_llm=int(raw["max_candidates_for_llm"]),
        headline_count=int(raw["headline_count"]),
        brief_count=int(raw["brief_count"]),
        keyword_count=int(raw["keyword_count"]),
        article_char_limit=int(raw["article_char_limit"]),
        dedupe=DedupeConfig(**raw["dedupe"]),
        mail=MailConfig(**raw["mail"]),
        sources=sources,
        runtime=runtime,
    )

