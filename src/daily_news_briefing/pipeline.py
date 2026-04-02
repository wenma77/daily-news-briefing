from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .article import fetch_article_text
from .config import Settings
from .dedupe import build_fingerprint, dedupe_candidates
from .editor import AINewsEditor
from .llm import OpenAICompatibleClient
from .mailer import GenericSMTPMailer, QQSMTPMailer
from .models import ArticleCandidate, NewsletterDraft, SeenEvent
from .render import render_html, render_text
from .rss import fetch_feed_candidates
from .state import load_seen_events, recent_fingerprints, save_seen_events
from .utils import safe_filename, utc_now


@dataclass(slots=True)
class PipelineResult:
    draft: NewsletterDraft
    generated_at: datetime
    html_body: str
    text_body: str
    selected_fingerprints: list[SeenEvent]
    total_candidates: int
    deduped_candidates: int
    grouped_events: int


class NewsPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.editor = AINewsEditor(
            client=OpenAICompatibleClient(
                base_url=settings.runtime.openai_base_url,
                api_key=settings.runtime.openai_api_key,
                model=settings.runtime.openai_model,
            ),
            headline_count=settings.headline_count,
            brief_count=settings.brief_count,
            keyword_count=settings.keyword_count,
            event_similarity=settings.dedupe.event_similarity,
        )

    def generate(self) -> PipelineResult:
        candidates = self._collect_candidates()
        deduped = dedupe_candidates(candidates, title_similarity=self.settings.dedupe.title_similarity)
        llm_input = deduped[: self.settings.max_candidates_for_llm]

        cleaned = self.editor.clean_candidates(llm_input)
        seen = load_seen_events(self.settings.state_file)
        recent = recent_fingerprints(seen, retention_days=3)
        events = self.editor.group_events(cleaned, recent)

        date_label = datetime.now().strftime("%Y-%m-%d")
        draft = self.editor.draft_newsletter(
            events,
            date_label=date_label,
            subject_template=self.settings.mail.subject_template,
        )
        generated_at = utc_now()
        html_body = render_html(draft, generated_at)
        text_body = render_text(draft, generated_at)
        event_by_id = {event.event_id: event for event in events}
        selected_fingerprints = [
            SeenEvent(
                fingerprint=event_by_id[item.event_id].fingerprint or build_fingerprint(item.title, item.category),
                title=item.title,
                sent_at=generated_at,
            )
            for item in (draft.lead_items + draft.brief_items)
            if item.event_id in event_by_id
        ]

        return PipelineResult(
            draft=draft,
            generated_at=generated_at,
            html_body=html_body,
            text_body=text_body,
            selected_fingerprints=selected_fingerprints,
            total_candidates=len(candidates),
            deduped_candidates=len(deduped),
            grouped_events=len(events),
        )

    def preview(self, output_path: Path | None = None) -> Path:
        self._validate_ai_env()
        result = self.generate()
        self.settings.output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_path or (self.settings.output_dir / f"{safe_filename(result.draft.subject)}.html")
        final_path.write_text(result.html_body, encoding="utf-8")
        final_path.with_suffix(".txt").write_text(result.text_body, encoding="utf-8")
        return final_path

    def send_test(self) -> None:
        self._validate_mail_env()
        now = datetime.now(UTC)
        draft = NewsletterDraft(
            subject="测试邮件：每日重点新闻简报",
            overview="这是一封测试邮件，用来验证 SMTP 配置是否正确。",
            lead_items=[],
            brief_items=[],
            keywords=["测试", "SMTP"],
        )
        self._mailer().send(
            mail_from=self.settings.runtime.mail_from,
            mail_to=self.settings.runtime.mail_to,
            subject=draft.subject,
            html_body=render_html(draft, now),
            text_body=render_text(draft, now),
        )

    def run(self) -> PipelineResult:
        self._validate_ai_env()
        self._validate_mail_env()
        result = self.generate()
        self._mailer().send(
            mail_from=self.settings.runtime.mail_from,
            mail_to=self.settings.runtime.mail_to,
            subject=result.draft.subject,
            html_body=result.html_body,
            text_body=result.text_body,
        )
        existing = load_seen_events(self.settings.state_file)
        save_seen_events(self.settings.state_file, existing + result.selected_fingerprints, retention_days=3)
        return result

    def _collect_candidates(self) -> list[ArticleCandidate]:
        candidates: list[ArticleCandidate] = []
        for source in self.settings.sources:
            try:
                source_candidates = fetch_feed_candidates(
                    source,
                    max_items=self.settings.max_candidates_per_source,
                    recency_hours=self.settings.recency_hours,
                )
            except Exception:
                continue
            for item in source_candidates:
                try:
                    article_text, source_kind = fetch_article_text(item.url, char_limit=self.settings.article_char_limit)
                except Exception:
                    article_text, source_kind = "", "feed"
                item.article_text = article_text
                item.article_text_source = source_kind
            candidates.extend(source_candidates)
        return candidates

    def _mailer(self) -> GenericSMTPMailer:
        runtime = self.settings.runtime
        if runtime.smtp_host.strip().lower() == "smtp.qq.com":
            return QQSMTPMailer(
                username=runtime.smtp_user,
                password=runtime.smtp_pass,
                host=runtime.smtp_host,
                port=runtime.smtp_port,
            )
        return GenericSMTPMailer(
            host=runtime.smtp_host,
            port=runtime.smtp_port,
            username=runtime.smtp_user,
            password=runtime.smtp_pass,
            use_ssl=runtime.smtp_port == 465,
        )

    def _validate_ai_env(self) -> None:
        missing = self.settings.runtime.missing_ai()
        if missing:
            raise RuntimeError("缺少 AI 相关环境变量：" + ", ".join(missing))

    def _validate_mail_env(self) -> None:
        missing = self.settings.runtime.missing_mail()
        if missing:
            raise RuntimeError("缺少邮件相关环境变量：" + ", ".join(missing))

