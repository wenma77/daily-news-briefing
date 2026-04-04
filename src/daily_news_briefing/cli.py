from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_settings
from .pipeline import NewsPipeline
from .utils import safe_filename


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="每日重点新闻邮件推送工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preview = subparsers.add_parser("preview", help="抓取新闻并生成本地 HTML 预览")
    preview.add_argument("--output", help="指定 HTML 输出路径")

    subparsers.add_parser("run", help="抓取、总结、发送，并更新已发送状态")
    subparsers.add_parser("send-test", help="只发送测试邮件，验证 SMTP 是否正常")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings()
    pipeline = NewsPipeline(settings)

    if args.command == "preview":
        output = Path(args.output) if args.output else None
        result = pipeline.generate()
        final_path = output or (settings.output_dir / f"{safe_filename(result.draft.subject)}.html")
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        final_path.write_text(result.html_body, encoding="utf-8")
        final_path.with_suffix(".txt").write_text(result.text_body, encoding="utf-8")
        payload = _result_payload(result)
        payload["preview_path"] = str(final_path)
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if args.command == "send-test":
        pipeline.send_test()
        print(json.dumps({"status": "ok", "message": "测试邮件已发送"}, ensure_ascii=False))
        return 0

    if args.command == "run":
        result = pipeline.run()
        print(json.dumps(_result_payload(result), ensure_ascii=False))
        return 0

    parser.error("未知命令")
    return 2


def _result_payload(result) -> dict:
    return {
        "status": "ok",
        "subject": result.draft.subject,
        "total_candidates": result.total_candidates,
        "deduped_candidates": result.deduped_candidates,
        "cleaned_candidates": result.cleaned_candidates,
        "grouped_events": result.grouped_events,
        "curated_events": result.curated_events,
        "lead_count": len(result.draft.lead_items),
        "brief_count": len(result.draft.brief_items),
        "watch_count": len(result.draft.watch_items),
        "official_source_hits": result.official_source_hits,
        "items_with_domestic_reference": result.items_with_domestic_reference,
        "lead_family_counts": result.lead_family_counts,
        "source_zero_hits": result.source_zero_hits,
        "google_news_primary_links": result.google_news_primary_links,
        "source_counts": result.source_counts,
        "health_warnings": result.health_warnings,
    }


def _summary_markdown_from_payload(payload: dict) -> str:
    lines = [
        "## Daily News Briefing Summary",
        "",
        f"- 主题：`{payload.get('subject', '')}`",
        f"- 总候选数：`{payload.get('total_candidates', 0)}`",
        f"- 去重后：`{payload.get('deduped_candidates', 0)}`",
        f"- 清洗后：`{payload.get('cleaned_candidates', 0)}`",
        f"- 事件聚合数：`{payload.get('grouped_events', 0)}`",
        f"- 终审事件数：`{payload.get('curated_events', 0)}`",
        f"- 今日重点：`{payload.get('lead_count', 0)}`",
        f"- 新闻速览：`{payload.get('brief_count', 0)}`",
        f"- 今日关注点：`{payload.get('watch_count', 0)}`",
        f"- 命中官方源：`{payload.get('official_source_hits', 0)}`",
        f"- 带国内参考的条目：`{payload.get('items_with_domestic_reference', 0)}`",
        f"- Google News 主链接数：`{payload.get('google_news_primary_links', 0)}`",
        "",
        "### Lead Family Counts",
    ]
    family_counts = payload.get("lead_family_counts", {}) or {}
    if isinstance(family_counts, dict) and family_counts:
        for family, count in family_counts.items():
            lines.append(f"- `{family}`: `{count}`")
    else:
        lines.append("- 无")

    lines.extend(
        [
            "",
        "### Source Counts",
        ]
    )
    source_counts = payload.get("source_counts", {}) or {}
    if isinstance(source_counts, dict) and source_counts:
        for source, count in source_counts.items():
            lines.append(f"- `{source}`: `{count}`")
    else:
        lines.append("- 无")

    zero_hits = payload.get("source_zero_hits", []) or []
    lines.append("")
    lines.append("### Zero-hit Sources")
    if zero_hits:
        for source in zero_hits:
            lines.append(f"- {source}")
    else:
        lines.append("- 无")

    warnings = payload.get("health_warnings", []) or []
    lines.append("")
    lines.append("### Health Warnings")
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- 无")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
