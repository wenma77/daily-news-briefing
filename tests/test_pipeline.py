from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from email import message_from_string
from email.header import decode_header
from pathlib import Path
from unittest.mock import patch

import _path_setup

from daily_news_briefing.config import DedupeConfig, MailConfig, RuntimeEnv, ScheduleConfig, Settings
from daily_news_briefing.models import ArticleCandidate, EventCard, FeedSource, NewsletterDraft, NewsletterItem
from daily_news_briefing.editor import AINewsEditor
from daily_news_briefing.pipeline import NewsPipeline


def _decode_mime_header(value: str) -> str:
    parts: list[str] = []
    for chunk, encoding in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(encoding or "utf-8", errors="ignore"))
        else:
            parts.append(chunk)
    return "".join(parts)


def _settings(project_root: Path) -> Settings:
    return Settings(
        project_root=project_root,
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


class PipelineIntegrationTests(unittest.TestCase):
    def test_preview_generates_html_and_txt(self) -> None:
        root = _path_setup.ROOT
        settings = _settings(root)
        pipeline = NewsPipeline(settings)

        candidates = [
            ArticleCandidate(
                id="a1",
                title="央行公布重要政策",
                source="测试源",
                publisher="新华社",
                published_at=datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
                url="https://example.com/a1",
                feed_summary="政策面出现变化",
                category_hint="财经",
                article_text="政策面出现变化，影响金融市场预期。",
                article_text_source="article",
            )
        ]
        events = [
            EventCard(
                event_id="E1",
                title="央行公布重要政策",
                category="财经",
                importance_score=90,
                summary="央行发布新的政策工具安排，市场关注后续影响。",
                article_ids=["a1"],
                representative_url="https://example.com/a1",
                source_name="新华社",
                domestic_reference_url="",
                domestic_reference_name="",
                fingerprint="fp1",
            )
        ]
        draft = NewsletterDraft(
            subject="[2026-04-02] 每日重点新闻简报",
            overview="今天的重要新闻主要集中在财经领域。",
            lead_items=[
                NewsletterItem(
                    event_id="E1",
                    title="央行公布重要政策",
                    summary="央行发布新的政策工具安排，市场关注后续影响。",
                    link="https://example.com/a1",
                    category="财经",
                    source_name="新华社",
                    domestic_reference_url="",
                    domestic_reference_name="",
                )
            ],
            brief_items=[],
            watch_items=["关注后续流动性投放节奏。"],
            keywords=["财经"],
        )

        output_path = root / "preview-test.html"
        with (
            patch.object(NewsPipeline, "_collect_candidates", return_value=candidates),
            patch.object(AINewsEditor, "clean_candidates", return_value=candidates),
            patch.object(AINewsEditor, "group_events", return_value=events),
            patch.object(AINewsEditor, "curate_events", return_value=events),
            patch.object(AINewsEditor, "draft_newsletter", return_value=draft),
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch("pathlib.Path.write_text", return_value=1) as mock_write_text,
        ):
            final_path = pipeline.preview(output_path=output_path)

        self.assertEqual(final_path, output_path)
        mock_mkdir.assert_called()
        written_paths = [str(call.args[0]) for call in mock_write_text.call_args_list]
        self.assertIn("<html", written_paths[0])
        self.assertTrue(any("今日重点" in text or "每日重点新闻" in text for text in written_paths))
        self.assertTrue(any("今日关注点" in text for text in written_paths))
        self.assertEqual(len(mock_write_text.call_args_list), 2)

    def test_generate_exposes_health_and_source_stats(self) -> None:
        root = _path_setup.ROOT
        settings = _settings(root)
        settings.sources = [
            FeedSource(
                name="中国人民银行首页公开信息",
                url="https://www.pbc.gov.cn/rmyh/index.html",
                category_hint="财经",
                fetcher="html_list",
                parser="pbc_home_updates",
                tier="S",
                role="official",
            )
        ]
        pipeline = NewsPipeline(settings)

        candidates = [
            ArticleCandidate(
                id="a1",
                title="央行公布重要政策",
                source="中国人民银行首页公开信息",
                publisher="中国人民银行首页公开信息",
                published_at=datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
                url="https://www.pbc.gov.cn/a1",
                feed_summary="政策面出现变化",
                category_hint="财经",
                article_text="政策面出现变化，影响金融市场预期。",
                article_text_source="article",
            )
        ]
        events = [
            EventCard(
                event_id="E1",
                title="央行公布重要政策",
                category="财经",
                importance_score=90,
                summary="央行发布新的政策工具安排，市场关注后续影响。",
                article_ids=["a1"],
                representative_url="https://www.pbc.gov.cn/a1",
                source_name="中国人民银行首页公开信息",
                domestic_reference_url="",
                domestic_reference_name="",
                fingerprint="fp1",
            )
        ]
        draft = NewsletterDraft(
            subject="[2026-04-02] 每日重点新闻简报",
            overview="今天的重要新闻主要集中在财经领域。",
            lead_items=[
                NewsletterItem(
                    event_id="E1",
                    title="央行公布重要政策",
                    summary="央行发布新的政策工具安排，市场关注后续影响。",
                    link="https://www.pbc.gov.cn/a1",
                    category="财经",
                    source_name="中国人民银行首页公开信息",
                )
            ],
            brief_items=[],
            watch_items=["关注后续流动性投放节奏。"],
            keywords=["财经"],
        )

        with (
            patch.object(NewsPipeline, "_collect_candidates", return_value=candidates),
            patch.object(NewsPipeline, "_enrich_candidates", side_effect=lambda x: x),
            patch.object(AINewsEditor, "clean_candidates", return_value=candidates),
            patch.object(AINewsEditor, "group_events", return_value=events),
            patch.object(AINewsEditor, "curate_events", return_value=events),
            patch.object(AINewsEditor, "draft_newsletter", return_value=draft),
        ):
            result = pipeline.generate()

        self.assertEqual(result.cleaned_candidates, 1)
        self.assertEqual(result.curated_events, 1)
        self.assertEqual(result.source_counts["中国人民银行首页公开信息"], 1)
        self.assertGreaterEqual(result.official_source_hits, 1)
        self.assertIn("policy", result.lead_family_counts)
        self.assertEqual(result.google_news_primary_links, 0)
        self.assertEqual(result.source_zero_hits, [])

    def test_send_test_uses_html_and_plain_bodies(self) -> None:
        settings = _settings(_path_setup.ROOT)
        pipeline = NewsPipeline(settings)

        with patch("daily_news_briefing.mailer.smtplib.SMTP_SSL") as smtp_ssl:
            server = smtp_ssl.return_value.__enter__.return_value
            pipeline.send_test()

        server.login.assert_called_once_with("sender@qq.com", "pass")
        send_args = server.sendmail.call_args.args
        message = message_from_string(send_args[2])
        self.assertEqual(send_args[0], "sender@qq.com")
        self.assertEqual(send_args[1], ["receiver@example.com"])
        self.assertEqual(_decode_mime_header(message["Subject"]), "测试邮件：每日重点新闻简报")
        self.assertIn("Content-Type: text/html", send_args[2])
        self.assertIn("Content-Type: text/plain", send_args[2])


class EditorPolicyTests(unittest.TestCase):
    def _editor(self) -> AINewsEditor:
        return AINewsEditor(
            client=object(),  # type: ignore[arg-type]
            headline_count=8,
            brief_count=16,
            keyword_count=5,
            event_similarity=0.78,
        )

    def test_disallowed_domain_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a1",
            title="OpenAI 完成一轮大额融资",
            source="测试源",
            publisher="InfoQ",
            published_at=datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
            url="https://www.infoq.cn/article/test",
            feed_summary="融资消息引发市场关注。",
            category_hint="科技",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_watch_items_are_built_from_major_events(self) -> None:
        editor = self._editor()
        events = [
            EventCard(
                event_id="E1",
                title="WTI 原油价格大涨",
                category="国际",
                importance_score=92,
                summary="原油大涨带动避险情绪升温。",
                article_ids=["a1"],
                representative_url="https://www.cls.cn/detail/1",
                source_name="财联社",
                domestic_reference_url="",
                domestic_reference_name="",
                fingerprint="fp1",
            ),
            EventCard(
                event_id="E2",
                title="央行开展中期借贷便利操作",
                category="财经",
                importance_score=88,
                summary="流动性安排受到市场关注。",
                article_ids=["a2"],
                representative_url="https://www.stcn.com/detail/2",
                source_name="证券时报",
                domestic_reference_url="",
                domestic_reference_name="",
                fingerprint="fp2",
            ),
        ]
        watch_items = editor._build_watch_items(events)
        self.assertTrue(any("油价" in item for item in watch_items))
        self.assertTrue(any("流动性" in item or "利率" in item for item in watch_items))

    def test_health_warnings_when_all_direct_official_sources_missing(self) -> None:
        sources = [
            type("S", (), {"name": "商务部新闻发布", "role": "official", "fetcher": "html_list"})(),
            type("S", (), {"name": "工信部新闻发布会", "role": "official", "fetcher": "html_list"})(),
            type("S", (), {"name": "中国人民银行首页公开信息", "role": "official", "fetcher": "html_list"})(),
        ]
        warnings = NewsPipeline._health_warnings(
            source_counts={
                "Google News 国内官方要闻": 10,
                "商务部新闻发布": 0,
                "工信部新闻发布会": 0,
                "中国人民银行首页公开信息": 0,
            },
            total_candidates=20,
            sources=sources,
            google_news_primary_links=0,
        )
        self.assertTrue(any("所有直连官方源" in item for item in warnings))

    def test_lead_family_cap_keeps_front_page_diverse(self) -> None:
        editor = self._editor()
        events = [
            EventCard(
                event_id="E1",
                title="国务院发布稳就业新政",
                category="国内",
                importance_score=95,
                summary="国务院发布稳就业新政，明确阶段性减负和重点群体就业支持安排。",
                article_ids=["a1"],
                representative_url="https://www.news.cn/1",
                source_name="新华网",
                fingerprint="fp1",
            ),
            EventCard(
                event_id="E2",
                title="特朗普称将扩大对华关税措施",
                category="国际",
                importance_score=93,
                summary="白宫释放更强硬的贸易政策信号，市场关注中美关系与全球供应链冲击。",
                article_ids=["a2"],
                representative_url="https://www.reuters.com/world/us/2",
                source_name="Reuters World",
                fingerprint="fp2",
            ),
            EventCard(
                event_id="E3",
                title="OpenAI 完成新一轮超大额融资",
                category="科技",
                importance_score=92,
                summary="AI 资本开支预期继续抬升。",
                article_ids=["a3"],
                representative_url="https://www.reuters.com/technology/3",
                source_name="Reuters Technology",
                fingerprint="fp3",
            ),
            EventCard(
                event_id="E4",
                title="重庆铁峰山隧道瓦斯爆炸事故已致多人遇难",
                category="国内",
                importance_score=91,
                summary="事故伤亡和应急处置进展已通报更新，相关责任调查继续推进。",
                article_ids=["a4"],
                representative_url="https://www.news.cn/4",
                source_name="新华网",
                fingerprint="fp4",
            ),
        ]
        event_map = {event.event_id: event for event in events}
        items = [
            NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=event.summary,
                link=event.representative_url,
                category=event.category,
                source_name=event.source_name,
            )
            for event in events
        ]
        selected = editor._apply_lead_family_cap(items, event_map)
        self.assertGreaterEqual(len(selected), 2)
        families = {editor.event_family(event_map[item.event_id]) for item in selected}
        self.assertIn("technology", families)
        self.assertIn("international_geopolitics", families)
        self.assertLessEqual(
            sum(1 for item in selected if editor.event_family(event_map[item.event_id]) == "market"),
            1,
        )

    def test_lead_family_cap_limits_central_bank_items(self) -> None:
        editor = self._editor()
        events = [
            EventCard(
                event_id="E1",
                title="央行召开例会部署货币政策",
                category="财经",
                importance_score=95,
                summary="央行例会释放政策信号。",
                article_ids=["a1"],
                representative_url="https://example.com/1",
                source_name="中国人民银行首页公开信息",
            ),
            EventCard(
                event_id="E2",
                title="央行新增数字人民币运营机构",
                category="财经",
                importance_score=93,
                summary="数字人民币生态继续扩围。",
                article_ids=["a2"],
                representative_url="https://example.com/2",
                source_name="中国人民银行首页公开信息",
            ),
            EventCard(
                event_id="E3",
                title="中东局势升级推高油价",
                category="国际",
                importance_score=92,
                summary="国际油价大幅上涨。",
                article_ids=["a3"],
                representative_url="https://example.com/3",
                source_name="财联社",
            ),
        ]
        event_map = {event.event_id: event for event in events}
        items = [
            NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=event.summary,
                link=event.representative_url,
                category=event.category,
                source_name=event.source_name,
            )
            for event in events
        ]
        selected = editor._apply_lead_family_cap(items, event_map)
        self.assertLessEqual(
            sum(1 for item in selected if "央行" in item.title or "人民币" in item.title),
            1,
        )

    def test_finalize_draft_removes_duplicate_brief_titles(self) -> None:
        editor = self._editor()
        events = [
            EventCard(
                event_id="E1",
                title="一季度A股IPO盘点",
                category="财经",
                importance_score=90,
                summary="A股IPO上会节奏变化。",
                article_ids=["a1"],
                representative_url="https://www.stcn.com/1",
                source_name="证券时报",
                fingerprint="fp1",
            ),
            EventCard(
                event_id="E2",
                title="一季度A股IPO盘点",
                category="财经",
                importance_score=88,
                summary="A股IPO上会节奏变化。",
                article_ids=["a2"],
                representative_url="https://www.21jingji.com/2",
                source_name="21财经",
                fingerprint="fp2",
            ),
        ]
        draft = NewsletterDraft(
            subject="测试日报",
            overview="概览",
            lead_items=[],
            brief_items=[
                NewsletterItem(
                    event_id="E1",
                    title="一季度A股IPO盘点",
                    summary="A股IPO上会节奏变化。",
                    link="https://www.stcn.com/1",
                    category="财经",
                    source_name="证券时报",
                ),
                NewsletterItem(
                    event_id="E2",
                    title="一季度A股IPO盘点",
                    summary="A股IPO上会节奏变化。",
                    link="https://www.21jingji.com/2",
                    category="财经",
                    source_name="21财经",
                ),
            ],
        )
        finalized = editor._finalize_draft(draft, events, "2026-04-02", "[{date}] 每日重点新闻简报")
        self.assertEqual(len(finalized.brief_items), 1)

    def test_routine_finance_candidates_are_downgraded(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a1",
            title="央行发布新一批LPR报价行名单",
            source="中国人民银行首页公开信息",
            publisher="中国人民银行首页公开信息",
            published_at=datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
            url="https://www.pbc.gov.cn/test",
            feed_summary="贷款市场报价利率报价行名单发布。",
            category_hint="财经",
        )
        self.assertLess(editor.quality_score(candidate), 1)

    def test_weak_public_service_candidates_are_downgraded(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a2",
            title="教育部：持续完善孤独症儿童教育保障体系 17所独立设置的特殊教育学校已建成",
            source="新华网",
            publisher="新华网",
            published_at=datetime(2026, 4, 3, 0, 0, tzinfo=UTC),
            url="https://www.news.cn/test",
            feed_summary="持续完善保障体系。",
            category_hint="国内",
        )
        self.assertLess(editor.quality_score(candidate), 1)

    def test_weak_service_notice_candidate_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a3",
            title="全国中小学生安全教育周活动展开",
            source="新华网",
            publisher="新华网",
            published_at=datetime(2026, 4, 3, 0, 0, tzinfo=UTC),
            url="https://www.news.cn/test-safe-week",
            feed_summary="有关部门组织开展安全教育周活动。",
            category_hint="国内",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_hard_information_rejects_weak_service_notice_terms(self) -> None:
        editor = self._editor()
        self.assertFalse(editor._has_hard_information("国家有关部门部署安全教育周工作", "组织开展宣传活动"))
        self.assertFalse(editor._has_hard_information("三部门开展专项行动", "推进工作部署"))

    def test_low_value_earnings_story_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a31",
            title="财报速递丨剥离医药商业板块后，达仁堂2025年营利双降",
            source="每日经济新闻",
            publisher="每日经济新闻",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://www.nbd.com.cn/test-earnings",
            feed_summary="公司披露年报后营利双降。",
            category_hint="财经",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_roundup_title_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a32",
            title="GPT周报｜OpenAI募资1220亿美元；阿里发布新模型Qwen 3.6-Plus；字节跳动赞助OpenClaw AI",
            source="财新",
            publisher="companies.caixin.com",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://companies.caixin.com/test-roundup",
            feed_summary="多条AI行业动态汇总。",
            category_hint="科技",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_weather_alert_service_candidate_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a33",
            title="河北启动重大气象灾害（大风）Ⅳ级应急响应",
            source="新华网",
            publisher="新华网",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://www.news.cn/test-weather",
            feed_summary="当地发布大风应急响应并加强值守。",
            category_hint="国内",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_education_admission_policy_notice_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a34",
            title="教育部严禁中小学意向登记提前招生",
            source="新华网",
            publisher="新华网",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://www.news.cn/test-admission",
            feed_summary="教育部要求严禁中小学意向登记提前招生。",
            category_hint="国内",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_technology_controversy_story_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a35",
            title="OpenAI收购科技播客TBPN引发争议 并购逻辑遭分析人士质疑",
            source="财联社",
            publisher="财联社",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://www.cls.cn/test-openai-controversy",
            feed_summary="这笔收购交易引发争议，并购逻辑遭分析人士质疑。",
            category_hint="科技",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_mixed_weak_technology_roundup_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a36",
            title="硬科技投向标|工信部：探索“算力银行”“算力超市”等创新业务 OpenAI完成1220亿美元融资",
            source="21财经",
            publisher="21财经",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://www.21jingji.com/test-tech-roundup",
            feed_summary="算力银行与OpenAI融资等多条科技动态被合并成一条栏目稿。",
            category_hint="科技",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_tv_program_style_title_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a37",
            title="[第一时间]意大利央行下调未来三年经济增长预期",
            source="央视网",
            publisher="央视网",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://tv.cctv.com/test-program",
            feed_summary="意大利央行下调未来三年经济增长预期。",
            category_hint="国际",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_column_prefix_title_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a39",
            title="【8点见】商务部：从未组织、参与或运营任何冠名“投资中国”字样的App应用",
            source="新京报",
            publisher="新京报",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://www.bjnews.com.cn/test-column-prefix",
            feed_summary="栏目稿形式报道商务部辟谣内容。",
            category_hint="国内",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_family_education_activity_title_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a41",
            title="临武：持续开展家庭教育指导服务实践活动",
            source="新华网",
            publisher="新华网",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://www.news.cn/test-family-education",
            feed_summary="地方持续开展家庭教育指导服务实践活动。",
            category_hint="国内",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_opinion_domain_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a40",
            title="陆挺：全球能源危机、电力供应与中国制造业的隐形优势",
            source="财新",
            publisher="财新",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://opinion.caixin.com/test-opinion",
            feed_summary="评论文章分析全球能源危机与中国制造业。",
            category_hint="国际",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_interview_style_title_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a42",
            title="中微董事长尹志尧，给半导体泼点冷水 | 海斌访谈",
            source="每日经济新闻",
            publisher="每日经济新闻",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://www.nbd.com.cn/test-interview",
            feed_summary="访谈文章讨论半导体行业观点。",
            category_hint="科技",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_service_card_title_is_blocked(self) -> None:
        editor = self._editor()
        candidate = ArticleCandidate(
            id="a43",
            title="海南银行发行社会保障卡一卡通",
            source="中新网",
            publisher="中新网",
            published_at=datetime(2026, 4, 4, 0, 0, tzinfo=UTC),
            url="https://www.chinanews.com.cn/test-card",
            feed_summary="海南银行发行社会保障卡一卡通。",
            category_hint="国内",
        )
        self.assertFalse(editor._passes_candidate_gate(candidate))

    def test_major_enterprise_event_can_enter_brief(self) -> None:
        editor = self._editor()
        event = EventCard(
            event_id="E39",
            title="Amazon正与Globalstar进行约90亿美元收购谈判",
            category="国际",
            importance_score=88,
            summary="Amazon据报正与Globalstar进行约90亿美元收购谈判，交易若成形将改变卫星通信竞争格局。",
            article_ids=["a39"],
            representative_url="https://news.google.com/rss/articles/amazon-test",
            source_name="Reuters Business",
        )
        self.assertTrue(editor._is_publishable_event(event, lead=False))

    def test_ai_face_theft_story_can_enter_brief(self) -> None:
        editor = self._editor()
        event = EventCard(
            event_id="E37",
            title="AI短剧“盗脸”乱象持续发酵",
            category="科技",
            importance_score=86,
            summary="AI短剧“盗脸”问题持续发酵，平台治理、肖像授权和侵权追责边界再受关注。",
            article_ids=["a37"],
            representative_url="https://www.bjnews.com.cn/detail/test-face-theft",
            source_name="新京报",
        )
        self.assertTrue(editor._is_publishable_event(event, lead=False))

    def test_us_chip_export_restriction_story_can_enter_brief(self) -> None:
        editor = self._editor()
        event = EventCard(
            event_id="E38",
            title="美国会两院两党推出新法案限制对华出口关键芯片制造设备",
            category="国际",
            importance_score=90,
            summary="美国会两院跨党派议员推动新法案，拟限制对华出口关键芯片制造设备，科技与经贸摩擦进一步升级。",
            article_ids=["a38"],
            representative_url="https://news.google.com/rss/articles/voa-test",
            source_name="美国之音",
        )
        self.assertTrue(editor._is_publishable_event(event, lead=False))

    def test_finalize_draft_rebalances_domestic_items_when_available(self) -> None:
        editor = self._editor()
        events = [
            EventCard(
                event_id="E40",
                title="泽连斯基称已向美国递交复活节停火提议",
                category="国际",
                importance_score=96,
                summary="停火斡旋继续拉锯，俄乌局势后续动向仍受关注。",
                article_ids=["a40"],
                representative_url="https://www.21jingji.com/test-40",
                source_name="21财经",
            ),
            EventCard(
                event_id="E41",
                title="重庆铁峰山隧道瓦斯爆炸事故被挂牌督办",
                category="国内",
                importance_score=92,
                summary="事故调查和责任追究进入更高等级跟踪，后续排查范围值得关注。",
                article_ids=["a41"],
                representative_url="https://www.news.cn/test-41",
                source_name="新华网",
            ),
            EventCard(
                event_id="E42",
                title="工信部：有攻击者利用针对苹果产品漏洞实施网络攻击，可窃取信息等",
                category="科技",
                importance_score=91,
                summary="工信部通报苹果产品漏洞遭利用并提醒加强防护，终端安全风险进一步受到关注。",
                article_ids=["a42"],
                representative_url="https://www.thepaper.cn/test-42",
                source_name="thepaper.cn",
            ),
            EventCard(
                event_id="E43",
                title="多部门启动中央储备冻猪肉收储",
                category="国内",
                importance_score=90,
                summary="多部门启动中央储备冻猪肉收储，释放稳价稳供信号。",
                article_ids=["a43"],
                representative_url="https://www.mofcom.gov.cn/test-43",
                source_name="商务部新闻发布",
            ),
        ]
        draft = NewsletterDraft(
            subject="测试日报",
            overview="概览",
            lead_items=[
                NewsletterItem(
                    event_id="E40",
                    title="泽连斯基称已向美国递交复活节停火提议",
                    summary="停火斡旋继续拉锯，俄乌局势后续动向仍受关注。",
                    link="https://www.21jingji.com/test-40",
                    category="国际",
                    source_name="21财经",
                )
            ],
            brief_items=[],
        )
        finalized = editor._finalize_draft(draft, events, "2026-04-04", "[{date}] 每日重点新闻简报")
        domestic_count = sum(1 for item in (finalized.lead_items + finalized.brief_items) if item.category == "国内")
        self.assertGreaterEqual(domestic_count, 2)

    def test_foreign_accident_report_is_not_counted_as_domestic_priority(self) -> None:
        editor = self._editor()
        event = EventCard(
            event_id="E44",
            title="巴西南部一小型飞机坠毁 机上4人全部遇难",
            category="国内",
            importance_score=85,
            summary="巴西南部一小型飞机坠毁，机上4人全部遇难。",
            article_ids=["a44"],
            representative_url="https://www.cctv.com/test-44",
            source_name="央视网",
        )
        self.assertFalse(editor._is_domestic_priority_event(event))
        self.assertFalse(editor._passes_event_gate(event))
        self.assertFalse(editor._is_publishable_event(event, lead=True))

    def test_finalize_draft_adds_domestic_item_to_lead_when_available(self) -> None:
        editor = self._editor()
        events = [
            EventCard(
                event_id="E45",
                title="泽连斯基称已向美国递交复活节停火提议",
                category="国际",
                importance_score=95,
                summary="停火斡旋继续拉锯，俄乌局势后续动向仍受关注。",
                article_ids=["a45"],
                representative_url="https://www.21jingji.com/test-45",
                source_name="21财经",
            ),
            EventCard(
                event_id="E46",
                title="特朗普总统对部分药品进口实施100%关税，同时调整金属关税",
                category="国际",
                importance_score=94,
                summary="美国关税路线继续加码，全球贸易与供应链预期再受冲击。",
                article_ids=["a46"],
                representative_url="https://www.voachinese.com/test-46",
                source_name="美国之音",
            ),
            EventCard(
                event_id="E47",
                title="市场监管总局通报44批次食品抽检不合格情况",
                category="国内",
                importance_score=90,
                summary="市场监管总局通报44批次食品抽检不合格情况，后续处罚与召回进展值得关注。",
                article_ids=["a47"],
                representative_url="https://www.cctv.com/test-47",
                source_name="央视网",
            ),
        ]
        draft = NewsletterDraft(
            subject="测试日报",
            overview="概览",
            lead_items=[
                NewsletterItem(
                    event_id="E45",
                    title="泽连斯基称已向美国递交复活节停火提议",
                    summary="停火斡旋继续拉锯，俄乌局势后续动向仍受关注。",
                    link="https://www.21jingji.com/test-45",
                    category="国际",
                    source_name="21财经",
                ),
                NewsletterItem(
                    event_id="E46",
                    title="特朗普总统对部分药品进口实施100%关税，同时调整金属关税",
                    summary="美国关税路线继续加码，全球贸易与供应链预期再受冲击。",
                    link="https://www.voachinese.com/test-46",
                    category="国际",
                    source_name="美国之音",
                ),
            ],
            brief_items=[],
        )
        finalized = editor._finalize_draft(draft, events, "2026-04-04", "[{date}] 每日重点新闻简报")
        self.assertTrue(any(item.category == "国内" for item in finalized.lead_items))

    def test_normalize_newsletter_item_falls_back_when_summary_equals_title(self) -> None:
        editor = self._editor()
        event = EventCard(
            event_id="E1",
            title="特朗普政府拟调整钢铝关税体系",
            category="国际",
            importance_score=90,
            summary="特朗普政府拟调整钢铝关税体系",
            article_ids=["a1"],
            representative_url="https://example.com/1",
            source_name="财联社",
        )
        item = NewsletterItem(
            event_id="E1",
            title="特朗普政府拟调整钢铝关税体系",
            summary="特朗普政府拟调整钢铝关税体系",
            link="https://example.com/1",
            category="国际",
            source_name="财联社",
        )
        normalized = editor._normalize_newsletter_item(item, event, long_summary=True)
        self.assertNotEqual(normalized.summary, "")
        self.assertNotEqual(normalized.summary, item.title)

    def test_fallback_summary_from_generic_title_returns_empty(self) -> None:
        editor = self._editor()
        self.assertEqual(editor._fallback_summary_from_title("全国中小学生安全教育周活动展开", 140), "")

    def test_clean_title_text_removes_column_suffix_and_video_note(self) -> None:
        editor = self._editor()
        cleaned = editor._clean_title_text("美伊停火斡旋陷入僵局 中东最大铝生产商工厂遭袭受损严重 | 环球市场（含视频）")
        self.assertEqual(cleaned, "美伊停火斡旋陷入僵局 中东最大铝生产商工厂遭袭受损严重")

    def test_best_event_summary_does_not_use_unrelated_article_text(self) -> None:
        editor = self._editor()
        representative = ArticleCandidate(
            id="a1",
            title="特朗普政府拟调整钢铝关税体系",
            source="The Paper",
            publisher="thepaper.cn",
            published_at=datetime(2026, 4, 3, 0, 0, tzinfo=UTC),
            url="https://example.com/tariff",
            feed_summary="特朗普政府拟调整钢铝关税体系。",
            category_hint="国际",
        )
        unrelated = ArticleCandidate(
            id="a2",
            title="中国与刚果（布）共同发展经济伙伴关系协定正式生效",
            source="商务部新闻发布",
            publisher="商务部新闻发布",
            published_at=datetime(2026, 4, 3, 0, 1, tzinfo=UTC),
            url="https://example.com/congo",
            feed_summary="协定正式生效，中方对刚方100%税目产品最终实现零关税。",
            category_hint="国内",
        )
        summary = editor._best_event_summary(
            [representative, unrelated],
            preferred="",
            title=representative.title,
            source_name="thepaper.cn",
            representative=representative,
            limit=160,
        )
        self.assertNotIn("刚果", summary)

    def test_summary_consistency_rejects_unrelated_preferred_summary(self) -> None:
        editor = self._editor()
        self.assertFalse(
            editor._summary_consistent_with_title(
                "特朗普政府拟调整钢铝关税体系",
                "中国与刚果（布）共同发展经济伙伴关系协定正式生效。",
            )
        )
        self.assertTrue(
            editor._summary_consistent_with_title(
                "特朗普政府拟调整钢铝关税体系",
                "特朗普政府拟调整钢铝关税体系，市场将继续关注其对关税和制造业成本的影响。",
            )
        )

    def test_lead_family_cap_limits_google_news_primary_links(self) -> None:
        editor = self._editor()
        events = [
            EventCard(
                event_id=f"E{i}",
                title=f"国际大事{i}",
                category="国际",
                importance_score=95 - i,
                summary=f"国际大事{i}影响全球市场。",
                article_ids=[f"a{i}"],
                representative_url=f"https://news.google.com/rss/articles/{i}",
                source_name="Google News 国际市场地缘",
                fingerprint=f"fp{i}",
            )
            for i in range(1, 5)
        ]
        event_map = {event.event_id: event for event in events}
        items = [
            NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=event.summary,
                link=event.representative_url,
                category=event.category,
                source_name=event.source_name,
            )
            for event in events
        ]
        selected = editor._apply_lead_family_cap(items, event_map)
        self.assertLessEqual(sum(1 for item in selected if "news.google.com" in item.link), 2)

    def test_selects_domestic_reference_for_international_event(self) -> None:
        editor = self._editor()
        articles = [
            ArticleCandidate(
                id="a1",
                title="中东局势推高油价",
                source="Reuters World",
                publisher="Reuters",
                published_at=datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
                url="https://www.reuters.com/world/test",
                feed_summary="油价上涨引发全球关注。",
                category_hint="国际",
                article_text="原油上涨并带动避险情绪升温。",
                article_text_source="article",
            ),
            ArticleCandidate(
                id="a2",
                title="中东局势推高油价",
                source="财联社",
                publisher="财联社",
                published_at=datetime(2026, 4, 2, 0, 5, tzinfo=UTC),
                url="https://www.cls.cn/detail/123",
                feed_summary="国内市场关注油价波动。",
                category_hint="国际",
                article_text="财联社对同一事件做出国内跟进报道。",
                article_text_source="article",
            ),
        ]
        domestic_url, domestic_name = editor._select_domestic_reference(articles, "https://www.reuters.com/world/test")
        self.assertEqual(domestic_url, "https://www.cls.cn/detail/123")
        self.assertEqual(domestic_name, "财联社")

    def test_weak_service_notice_event_is_not_publishable(self) -> None:
        editor = self._editor()
        event = EventCard(
            event_id="E3",
            title="交通部门多措施保出行",
            category="国内",
            importance_score=88,
            summary="清明假期前后，各地交通部门加强服务保障。",
            article_ids=["a3"],
            representative_url="https://www.news.cn/traffic",
            source_name="新华网",
        )
        self.assertFalse(editor._passes_event_gate(event))
        self.assertFalse(editor._is_publishable_event(event, lead=True))

    def test_soft_technology_event_is_not_publishable_as_lead(self) -> None:
        editor = self._editor()
        event = EventCard(
            event_id="E4",
            title="我国成立太空算力产业协同平台",
            category="科技",
            importance_score=90,
            summary="相关部门提出加快培育太空算力产业。",
            article_ids=["a4"],
            representative_url="https://www.news.cn/space-ai",
            source_name="新华网",
        )
        self.assertFalse(editor._passes_event_gate(event))
        self.assertFalse(editor._is_publishable_event(event, lead=True))

    def test_lead_prioritizes_two_hard_international_events_when_available(self) -> None:
        editor = self._editor()
        events = [
            EventCard(
                event_id="E10",
                title="特朗普称将扩大对华关税措施",
                category="国际",
                importance_score=97,
                summary="白宫释放更强硬贸易政策信号，市场关注中美关系与全球供应链影响。",
                article_ids=["a10"],
                representative_url="https://www.reuters.com/world/us/test-1",
                source_name="Reuters World",
            ),
            EventCard(
                event_id="E11",
                title="伊朗与以色列冲突升级引发停火谈判变数",
                category="国际",
                importance_score=96,
                summary="中东局势再度紧张，能源与避险情绪同步升温。",
                article_ids=["a11"],
                representative_url="https://www.reuters.com/world/middle-east/test-2",
                source_name="Reuters World",
            ),
            EventCard(
                event_id="E12",
                title="OpenAI推出新模型并上调企业服务价格",
                category="科技",
                importance_score=95,
                summary="OpenAI更新模型和商业化策略，企业级AI成本预期被重新评估。",
                article_ids=["a12"],
                representative_url="https://www.reuters.com/technology/test-3",
                source_name="Reuters Technology",
            ),
            EventCard(
                event_id="E13",
                title="全国中小学生安全教育周活动展开",
                category="国内",
                importance_score=99,
                summary="有关部门组织开展专题宣传活动。",
                article_ids=["a13"],
                representative_url="https://www.news.cn/test-4",
                source_name="新华网",
            ),
        ]
        event_map = {event.event_id: event for event in events}
        items = [
            NewsletterItem(
                event_id=event.event_id,
                title=event.title,
                summary=event.summary,
                link=event.representative_url,
                category=event.category,
                source_name=event.source_name,
            )
            for event in events
        ]
        selected = editor._apply_lead_family_cap(items, event_map)
        selected_titles = {item.title for item in selected}
        self.assertIn("特朗普称将扩大对华关税措施", selected_titles)
        self.assertIn("伊朗与以色列冲突升级引发停火谈判变数", selected_titles)
        self.assertNotIn("全国中小学生安全教育周活动展开", selected_titles)


if __name__ == "__main__":
    unittest.main()
