from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


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
    cleaned_candidates: int
    curated_events: int
    source_counts: dict[str, int]
    official_source_hits: int
    items_with_domestic_reference: int
    lead_family_counts: dict[str, int]
    source_zero_hits: list[str]
    google_news_primary_links: int
    health_warnings: list[str]


class NewsPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.editor = AINewsEditor(
            client=OpenAICompatibleClient(
                base_url=settings.runtime.openai_base_url,
                api_key=settings.runtime.openai_api_key,
                model=settings.runtime.openai_model,
                reasoning_effort=settings.runtime.openai_reasoning_effort,
            ),
            headline_count=settings.headline_count,
            brief_count=settings.brief_count,
            keyword_count=settings.keyword_count,
            event_similarity=settings.dedupe.event_similarity,
            source_registry={source.name: source for source in settings.sources},
        )

    def generate(self) -> PipelineResult:
        candidates = self._collect_candidates()
        source_counts = self._source_counts(candidates)
        deduped = dedupe_candidates(candidates, title_similarity=self.settings.dedupe.title_similarity)
        ranked = sorted(deduped, key=self.editor.quality_score, reverse=True)
        enriched = self._enrich_candidates(ranked[: max(self.settings.max_candidates_for_llm + 24, 80)])
        llm_input = enriched[: self.settings.max_candidates_for_llm]

        cleaned = self.editor.clean_candidates(llm_input)
        seen = load_seen_events(self.settings.state_file)
        recent = recent_fingerprints(seen, retention_days=3)
        grouped = self.editor.group_events(cleaned, recent)
        events = self.editor.curate_events(grouped)

        date_label = datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d")
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
        items_with_domestic_reference = sum(
            1 for item in (draft.lead_items + draft.brief_items) if item.domestic_reference_url
        )
        official_source_hits = self._official_source_hits(source_counts, self.settings.sources)
        source_zero_hits = self._source_zero_hits(source_counts, self.settings.sources)
        lead_family_counts = self._lead_family_counts(draft, event_by_id)
        google_news_primary_links = self._google_news_primary_links(draft)
        health_warnings = self._health_warnings(
            source_counts=source_counts,
            total_candidates=len(candidates),
            sources=self.settings.sources,
            google_news_primary_links=google_news_primary_links,
        )

        return PipelineResult(
            draft=draft,
            generated_at=generated_at,
            html_body=html_body,
            text_body=text_body,
            selected_fingerprints=selected_fingerprints,
            total_candidates=len(candidates),
            deduped_candidates=len(deduped),
            grouped_events=len(grouped),
            cleaned_candidates=len(cleaned),
            curated_events=len(events),
            source_counts=source_counts,
            official_source_hits=official_source_hits,
            items_with_domestic_reference=items_with_domestic_reference,
            lead_family_counts=lead_family_counts,
            source_zero_hits=source_zero_hits,
            google_news_primary_links=google_news_primary_links,
            health_warnings=health_warnings,
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
            candidates.extend(source_candidates)
        return candidates

    @staticmethod
    def _source_counts(candidates: list[ArticleCandidate]) -> dict[str, int]:
        return dict(Counter(item.source for item in candidates))

    @staticmethod
    def _official_source_hits(source_counts: dict[str, int], sources: list) -> int:
        official_names = {
            source.name
            for source in sources
            if getattr(source, "role", "discovery") == "official"
        }
        return sum(1 for source, count in source_counts.items() if source in official_names and count > 0)

    @staticmethod
    def _source_zero_hits(source_counts: dict[str, int], sources: list) -> list[str]:
        return [source.name for source in sources if source_counts.get(source.name, 0) == 0]

    def _lead_family_counts(self, draft: NewsletterDraft, event_by_id: dict[str, object]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for item in draft.lead_items:
            event = event_by_id.get(item.event_id)
            if event is None:
                continue
            counts[self.editor.event_family(event)] += 1
        return dict(counts)

    @staticmethod
    def _google_news_primary_links(draft: NewsletterDraft) -> int:
        return sum(
            1
            for item in (draft.lead_items + draft.brief_items)
            if "news.google.com" in item.link
        )

    @staticmethod
    def _health_warnings(
        *,
        source_counts: dict[str, int],
        total_candidates: int,
        sources: list,
        google_news_primary_links: int,
    ) -> list[str]:
        warnings: list[str] = []
        direct_official_sources = [
            source.name
            for source in sources
            if getattr(source, "role", "discovery") == "official" and getattr(source, "fetcher", "rss") == "html_list"
        ]
        missing_official = [source for source in direct_official_sources if source_counts.get(source, 0) == 0]
        if direct_official_sources and len(missing_official) == len(direct_official_sources):
            warnings.append("所有直连官方源今日均未产出候选。")
        elif missing_official:
            warnings.append("部分直连官方源今日未产出候选：" + "、".join(missing_official))
        if total_candidates < 40:
            warnings.append(f"总候选数偏低：{total_candidates}。")
        if google_news_primary_links > 0:
            warnings.append(f"部分最终条目仍使用 Google News 聚合链接：{google_news_primary_links} 条。")
        return warnings

    def _enrich_candidates(self, candidates: list[ArticleCandidate]) -> list[ArticleCandidate]:
        for item in candidates:
            if item.article_text or item.article_text_source != "feed":
                continue
            try:
                article_text, source_kind, resolved_url = fetch_article_text(
                    item.url,
                    char_limit=self.settings.article_char_limit,
                )
            except Exception:
                article_text, source_kind, resolved_url = "", "feed", item.url
            item.article_text = article_text
            item.article_text_source = source_kind
            item.url = resolved_url or item.url
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
