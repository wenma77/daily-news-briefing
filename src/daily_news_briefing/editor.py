from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass

from .dedupe import build_fingerprint, normalize_title, similarity
from .llm import LLMError, OpenAICompatibleClient
from .models import ArticleCandidate, EventCard, NewsletterDraft, NewsletterItem
from .utils import truncate_text

LOW_VALUE_KEYWORDS = {
    "优惠",
    "折扣",
    "促销",
    "广告",
    "直播带货",
    "种草",
    "抽奖",
    "娱乐八卦",
}


@dataclass(slots=True)
class AINewsEditor:
    client: OpenAICompatibleClient
    headline_count: int
    brief_count: int
    keyword_count: int
    event_similarity: float

    def clean_candidates(self, candidates: list[ArticleCandidate]) -> list[ArticleCandidate]:
        prompt_items = [item.to_prompt_dict() for item in candidates]
        system_prompt = (
            "你是严谨的中文新闻值班主编。"
            "请只保留真正重要、可信、信息量足够的新闻候选。"
            "禁止追逐八卦、营销稿、导购稿、纯观点稿。"
            "输出必须是 JSON。"
        )
        user_prompt = json.dumps(
            {
                "task": "从候选新闻中保留适合做每日重点新闻简报的条目。",
                "rules": [
                    "优先级：影响范围 > 时效性 > 后续影响 > 信息可信度",
                    "保留国内大事、国际局势、财经市场、科技行业重要动态",
                    "剔除明显重复、低质量转载、信息不足条目",
                    "输出字段 kept_ids，值为候选 id 数组",
                ],
                "candidates": prompt_items,
            },
            ensure_ascii=False,
        )
        try:
            data = self.client.request_json(system_prompt, user_prompt)
            kept_ids = {str(item).strip() for item in data.get("kept_ids", []) if str(item).strip()}
            cleaned = [item for item in candidates if item.id in kept_ids]
            if cleaned:
                return cleaned
        except LLMError:
            pass
        return self._heuristic_clean(candidates)

    def group_events(
        self,
        candidates: list[ArticleCandidate],
        seen_fingerprints: set[str],
    ) -> list[EventCard]:
        prompt_items = [item.to_prompt_dict() for item in candidates]
        system_prompt = (
            "你是中文新闻编辑台的统筹编辑。"
            "请把同一事件的多篇报道合并为事件卡片，并按重要性打分。"
            "输出必须是 JSON。"
        )
        user_prompt = json.dumps(
            {
                "task": "把候选新闻聚合为事件卡片。",
                "rules": [
                    "同一事件的多篇报道必须合并",
                    "importance_score 取 0 到 100 的整数",
                    "category 只用：国内、国际、财经、科技、其他",
                    "每个事件需要 title、summary、why_it_matters、article_ids",
                    "不要输出最近 3 天已经推送过的重复事件",
                ],
                "recent_sent_fingerprints": sorted(seen_fingerprints),
                "candidates": prompt_items,
            },
            ensure_ascii=False,
        )
        try:
            data = self.client.request_json(system_prompt, user_prompt)
            events = self._events_from_json(data, candidates, seen_fingerprints)
            if events:
                return events
        except LLMError:
            pass
        return self._heuristic_group(candidates, seen_fingerprints)

    def draft_newsletter(self, events: list[EventCard], date_label: str, subject_template: str) -> NewsletterDraft:
        prompt_items = [item.to_prompt_dict() for item in events]
        system_prompt = (
            "你是顶级中文新闻编辑，要写一封适合邮件推送的每日重点新闻简报。"
            "风格要克制、专业、信息密度高。"
            "输出必须是 JSON。"
        )
        user_prompt = json.dumps(
            {
                "task": "输出最终 newsletter。",
                "rules": [
                    f"lead_items 最多 {self.headline_count} 条",
                    f"brief_items 最多 {self.brief_count} 条，且不能与 lead_items 重复",
                    "每条都要包含 event_id、title、summary、why_important、link、category",
                    "lead_items 的 summary 用 80 到 140 字中文",
                    "brief_items 的 summary 用 30 到 60 字中文",
                    f"keywords 输出 3 到 {self.keyword_count} 个",
                    "overview 是 1 段中文，概括当天最重要趋势",
                    "如果当天有效事件不足，允许少于目标条数，禁止编造或重复填充",
                ],
                "subject_template": subject_template,
                "date": date_label,
                "events": prompt_items,
            },
            ensure_ascii=False,
        )
        try:
            data = self.client.request_json(system_prompt, user_prompt)
            draft = self._finalize_draft(
                self._build_draft_from_json(data, events, date_label, subject_template),
                events,
                date_label,
                subject_template,
            )
            if draft.lead_items:
                return draft
        except LLMError:
            pass
        return self._finalize_draft(
            self._heuristic_draft(events, date_label, subject_template),
            events,
            date_label,
            subject_template,
        )

    def _events_from_json(
        self,
        data: dict,
        candidates: list[ArticleCandidate],
        seen_fingerprints: set[str],
    ) -> list[EventCard]:
        by_id = {item.id: item for item in candidates}
        events: list[EventCard] = []
        for index, item in enumerate(data.get("events", []), start=1):
            article_ids = [str(article_id) for article_id in item.get("article_ids", []) if str(article_id) in by_id]
            if not article_ids:
                continue
            title = str(item.get("title", "")).strip() or by_id[article_ids[0]].title
            category = str(item.get("category", "")).strip() or by_id[article_ids[0]].category_hint
            fingerprint = build_fingerprint(title, category)
            if fingerprint in seen_fingerprints:
                continue
            events.append(
                EventCard(
                    event_id=f"E{index}",
                    title=title,
                    category=category,
                    importance_score=int(item.get("importance_score", 50)),
                    why_it_matters=truncate_text(str(item.get("why_it_matters", "")).strip(), 120),
                    summary=truncate_text(str(item.get("summary", "")).strip(), 160),
                    article_ids=article_ids,
                    representative_url=by_id[article_ids[0]].url,
                    fingerprint=fingerprint,
                )
            )
        return sorted(events, key=lambda event: event.importance_score, reverse=True)

    def _build_draft_from_json(
        self,
        data: dict,
        events: list[EventCard],
        date_label: str,
        subject_template: str,
    ) -> NewsletterDraft:
        event_map = {event.event_id: event for event in events}

        def build_item(raw_item: dict) -> NewsletterItem | None:
            event_id = str(raw_item.get("event_id", "")).strip()
            event = event_map.get(event_id)
            if not event:
                return None
            return NewsletterItem(
                event_id=event_id,
                title=str(raw_item.get("title", "")).strip() or event.title,
                summary=truncate_text(str(raw_item.get("summary", "")).strip() or event.summary, 160),
                why_important=truncate_text(str(raw_item.get("why_important", "")).strip() or event.why_it_matters, 120),
                link=str(raw_item.get("link", "")).strip() or event.representative_url,
                category=str(raw_item.get("category", "")).strip() or event.category,
            )

        lead_items = [item for item in (build_item(raw) for raw in data.get("lead_items", [])) if item]
        brief_items = [item for item in (build_item(raw) for raw in data.get("brief_items", [])) if item]
        seen_ids = {item.event_id for item in lead_items}
        brief_items = [item for item in brief_items if item.event_id not in seen_ids]

        return NewsletterDraft(
            subject=str(data.get("subject", "")).strip() or subject_template.format(date=date_label),
            overview=truncate_text(str(data.get("overview", "")).strip(), 220),
            lead_items=lead_items[: self.headline_count],
            brief_items=brief_items[: self.brief_count],
            keywords=[
                truncate_text(str(keyword).strip(), 18)
                for keyword in data.get("keywords", [])
                if str(keyword).strip()
            ][: self.keyword_count],
        )

    def _heuristic_clean(self, candidates: list[ArticleCandidate]) -> list[ArticleCandidate]:
        results: list[ArticleCandidate] = []
        for candidate in candidates:
            merged_text = f"{candidate.title} {candidate.feed_summary} {candidate.article_text}"
            if any(keyword in merged_text for keyword in LOW_VALUE_KEYWORDS):
                continue
            results.append(candidate)
        return results[: max(self.headline_count + self.brief_count + 8, 18)]

    def _heuristic_group(
        self,
        candidates: list[ArticleCandidate],
        seen_fingerprints: set[str],
    ) -> list[EventCard]:
        events: list[EventCard] = []
        groups: list[list[ArticleCandidate]] = []
        for candidate in sorted(candidates, key=lambda item: item.published_at, reverse=True):
            norm_title = normalize_title(candidate.title)
            matched_group: list[ArticleCandidate] | None = None
            for group in groups:
                if similarity(norm_title, normalize_title(group[0].title)) >= self.event_similarity:
                    matched_group = group
                    break
            if matched_group is None:
                groups.append([candidate])
            else:
                matched_group.append(candidate)

        for index, group in enumerate(groups, start=1):
            representative = group[0]
            category = representative.category_hint or "其他"
            fingerprint = build_fingerprint(representative.title, category)
            if fingerprint in seen_fingerprints:
                continue
            score = min(100, 50 + len(group) * 8 + (10 if category in {"国内", "国际", "财经", "科技"} else 0))
            events.append(
                EventCard(
                    event_id=f"E{index}",
                    title=representative.title,
                    category=category,
                    importance_score=score,
                    why_it_matters="影响范围较大，且仍在持续发酵，值得纳入今日重点关注。",
                    summary=truncate_text(representative.article_text or representative.feed_summary or representative.title, 140),
                    article_ids=[item.id for item in group],
                    representative_url=representative.url,
                    fingerprint=fingerprint,
                )
            )
        return sorted(events, key=lambda event: event.importance_score, reverse=True)

    def _heuristic_draft(
        self,
        events: list[EventCard],
        date_label: str,
        subject_template: str,
    ) -> NewsletterDraft:
        selected = sorted(events, key=lambda event: event.importance_score, reverse=True)
        lead_events = selected[: self.headline_count]
        brief_events = [event for event in selected if event.event_id not in {item.event_id for item in lead_events}]
        brief_events = brief_events[: self.brief_count]

        lead_items = [
            NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=truncate_text(event.summary, 140),
                why_important=truncate_text(event.why_it_matters, 100),
                link=event.representative_url,
                category=event.category,
            )
            for event in lead_events
        ]
        brief_items = [
            NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=truncate_text(event.summary, 60),
                why_important=truncate_text(event.why_it_matters, 60),
                link=event.representative_url,
                category=event.category,
            )
            for event in brief_events
        ]
        top_categories = [category for category, _count in Counter(event.category for event in selected[:10]).most_common(self.keyword_count)]
        overview = "今天的重要新闻主要集中在" + "、".join(top_categories or ["综合"]) + "领域，整体呈现高影响事件偏多、市场与科技消息并行的格局。"
        return NewsletterDraft(
            subject=subject_template.format(date=date_label),
            overview=overview,
            lead_items=lead_items,
            brief_items=brief_items,
            keywords=top_categories[: self.keyword_count],
        )

    def _finalize_draft(
        self,
        draft: NewsletterDraft,
        events: list[EventCard],
        date_label: str,
        subject_template: str,
    ) -> NewsletterDraft:
        available_events = sorted(events, key=lambda event: event.importance_score, reverse=True)
        event_map = {event.event_id: event for event in available_events}

        def unique_items(items: list[NewsletterItem]) -> list[NewsletterItem]:
            seen: set[str] = set()
            results: list[NewsletterItem] = []
            for item in items:
                if item.event_id in seen:
                    continue
                if item.event_id not in event_map:
                    continue
                seen.add(item.event_id)
                results.append(item)
            return results

        lead_items = unique_items(draft.lead_items)
        used_ids = {item.event_id for item in lead_items}
        brief_items = [item for item in unique_items(draft.brief_items) if item.event_id not in used_ids]
        used_ids.update(item.event_id for item in brief_items)

        def fallback_item(event: EventCard, *, long_summary: bool) -> NewsletterItem:
            return NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=truncate_text(event.summary, 140 if long_summary else 60),
                why_important=truncate_text(event.why_it_matters, 100 if long_summary else 60),
                link=event.representative_url,
                category=event.category,
            )

        for event in available_events:
            if len(lead_items) >= self.headline_count:
                break
            if event.event_id in used_ids:
                continue
            lead_items.append(fallback_item(event, long_summary=True))
            used_ids.add(event.event_id)

        for event in available_events:
            if len(brief_items) >= self.brief_count:
                break
            if event.event_id in used_ids:
                continue
            brief_items.append(fallback_item(event, long_summary=False))
            used_ids.add(event.event_id)

        overview = draft.overview.strip()
        if not overview:
            overview = "今天的重要新闻已按影响范围和可信度整理，以下为可验证的重点事件。"

        available_count = len(available_events)
        target_count = self.headline_count + self.brief_count
        if available_count < target_count:
            shortage_note = f"今日有效事件仅 {available_count} 条，本期简报按可验证内容生成，未补造不足条目。"
            if shortage_note not in overview:
                overview = truncate_text(f"{overview} {shortage_note}", 220)

        keywords = [keyword for keyword in draft.keywords if keyword]
        if not keywords:
            keywords = [category for category, _count in Counter(event.category for event in available_events).most_common(self.keyword_count)]

        return NewsletterDraft(
            subject=draft.subject or subject_template.format(date=date_label),
            overview=overview,
            lead_items=lead_items[: self.headline_count],
            brief_items=brief_items[: self.brief_count],
            keywords=keywords[: self.keyword_count],
        )
