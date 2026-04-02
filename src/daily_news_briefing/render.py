from __future__ import annotations

import html
from datetime import datetime

from .models import NewsletterDraft


def render_html(draft: NewsletterDraft, generated_at: datetime) -> str:
    keywords = "".join(
        f'<span style="display:inline-block;margin:0 8px 8px 0;padding:6px 10px;border-radius:999px;background:#eef4ff;color:#1d4ed8;font-size:12px;">{html.escape(keyword)}</span>'
        for keyword in draft.keywords
    )
    lead_items = "".join(_render_html_item(item, lead=True) for item in draft.lead_items)
    brief_items = "".join(_render_html_item(item, lead=False) for item in draft.brief_items)
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(draft.subject)}</title>
  </head>
  <body style="margin:0;padding:0;background:#f6f8fb;font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:#162033;">
    <div style="max-width:760px;margin:0 auto;padding:24px 16px 40px;">
      <div style="background:linear-gradient(135deg,#0f172a,#1e3a8a);padding:28px;border-radius:20px;color:#fff;box-shadow:0 18px 50px rgba(15,23,42,0.18);">
        <div style="font-size:13px;opacity:0.85;">每日重点新闻简报</div>
        <h1 style="margin:10px 0 8px;font-size:28px;line-height:1.3;">{html.escape(draft.subject)}</h1>
        <p style="margin:0;font-size:15px;line-height:1.8;opacity:0.95;">{html.escape(draft.overview)}</p>
        <div style="margin-top:18px;">{keywords}</div>
      </div>
      <div style="margin-top:18px;padding:20px 22px;border-radius:18px;background:#ffffff;box-shadow:0 14px 40px rgba(15,23,42,0.06);">
        <h2 style="margin:0 0 16px;font-size:20px;color:#0f172a;">核心头条</h2>
        {lead_items}
      </div>
      <div style="margin-top:18px;padding:20px 22px;border-radius:18px;background:#ffffff;box-shadow:0 14px 40px rgba(15,23,42,0.06);">
        <h2 style="margin:0 0 16px;font-size:20px;color:#0f172a;">重要快讯</h2>
        {brief_items}
      </div>
      <div style="margin-top:18px;padding:14px 18px;border-radius:16px;background:#eaf1ff;color:#334155;font-size:12px;line-height:1.8;">
        生成时间：{html.escape(generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"))}<br>
        提示：本邮件由自动化新闻编辑流水线生成，建议点击原文链接核对细节。
      </div>
    </div>
  </body>
</html>"""


def _render_html_item(item, lead: bool) -> str:
    title_size = "20px" if lead else "17px"
    summary_size = "15px" if lead else "14px"
    return f"""
      <div style="padding:18px 0;border-top:1px solid #e5e7eb;">
        <div style="margin-bottom:8px;">
          <span style="display:inline-block;padding:4px 8px;border-radius:999px;background:#f1f5f9;color:#475569;font-size:12px;">{html.escape(item.category)}</span>
        </div>
        <div style="font-size:{title_size};font-weight:700;line-height:1.6;color:#0f172a;">{html.escape(item.title)}</div>
        <div style="margin-top:10px;font-size:{summary_size};line-height:1.9;color:#334155;">{html.escape(item.summary)}</div>
        <div style="margin-top:8px;font-size:13px;line-height:1.8;color:#475569;">为什么重要：{html.escape(item.why_important)}</div>
        <div style="margin-top:10px;"><a href="{html.escape(item.link)}" style="color:#2563eb;text-decoration:none;font-weight:600;">查看原文</a></div>
      </div>"""


def render_text(draft: NewsletterDraft, generated_at: datetime) -> str:
    lines = [draft.subject, "", draft.overview, ""]
    if draft.keywords:
        lines.append("关键词：" + " / ".join(draft.keywords))
        lines.append("")
    lines.append("核心头条")
    for item in draft.lead_items:
        lines.extend(
            [
                f"- [{item.category}] {item.title}",
                f"  摘要：{item.summary}",
                f"  为什么重要：{item.why_important}",
                f"  原文：{item.link}",
            ]
        )
    lines.append("")
    lines.append("重要快讯")
    for item in draft.brief_items:
        lines.extend(
            [
                f"- [{item.category}] {item.title}",
                f"  摘要：{item.summary}",
                f"  原文：{item.link}",
            ]
        )
    lines.append("")
    lines.append("生成时间：" + generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"))
    return "\n".join(lines)
