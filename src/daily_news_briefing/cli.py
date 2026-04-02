from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_settings
from .pipeline import NewsPipeline


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
        final_path = pipeline.preview(output_path=output)
        print(json.dumps({"status": "ok", "preview_path": str(final_path)}, ensure_ascii=False))
        return 0

    if args.command == "send-test":
        pipeline.send_test()
        print(json.dumps({"status": "ok", "message": "测试邮件已发送"}, ensure_ascii=False))
        return 0

    if args.command == "run":
        result = pipeline.run()
        print(
            json.dumps(
                {
                    "status": "ok",
                    "subject": result.draft.subject,
                    "total_candidates": result.total_candidates,
                    "deduped_candidates": result.deduped_candidates,
                    "grouped_events": result.grouped_events,
                    "lead_count": len(result.draft.lead_items),
                    "brief_count": len(result.draft.brief_items),
                },
                ensure_ascii=False,
            )
        )
        return 0

    parser.error("未知命令")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
