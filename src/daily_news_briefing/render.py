from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

from .models import NewsletterDraft

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def render_html(draft: NewsletterDraft, generated_at: datetime) -> str:
    keywords = "".join(
        f'<span style="display:inline-block;margin:0 8px 8px 0;padding:6px 10px;border-radius:999px;background:#eef4ff;color:#1d4ed8;font-size:12px;">{html.escape(keyword)}</span>'
        for keyword in draft.keywords
    )
    lead_items = "".join(_render_html_item(item, lead=True) for item in draft.lead_items)
    brief_items = "".join(_render_html_item(item, lead=False) for item in draft.brief_items)
    watch_items = "".join(
        f'<li style="margin:0 0 8px 18px;color:#334155;line-height:1.8;">{html.escape(item)}</li>'
        for item in draft.watch_items
    )
    watch_section = ""
    if watch_items:
        watch_section = f"""
      <div style="margin-top:18px;padding:18px 22px;border-radius:18px;background:#ffffff;box-shadow:0 14px 40px rgba(15,23,42,0.06);">
        <h2 style="margin:0 0 12px;font-size:18px;color:#0f172a;">今日关注点</h2>
        <ul style="margin:0;padding:0;list-style-position:outside;">
          {watch_items}
        </ul>
      </div>"""
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(draft.subject)}</title>
  </head>
  <body style="margin:0;padding:0;background:#f3f6fb;font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;color:#162033;">
    <div style="max-width:760px;margin:0 auto;padding:24px 16px 40px;">
      <div style="background:#ffffff;padding:28px;border-radius:20px;color:#162033;border:1px solid #dbe4f0;box-shadow:0 18px 50px rgba(15,23,42,0.08);">
        <div style="font-size:13px;color:#475569;">每日重点新闻简报 | 政策、市场与科技动态</div>
        <h1 style="margin:10px 0 8px;font-size:28px;line-height:1.3;color:#0f172a;">{html.escape(draft.subject)}</h1>
        <div style="margin:10px 0 8px;font-size:13px;font-weight:700;letter-spacing:0.04em;color:#1d4ed8;">今日主线</div>
        <p style="margin:0;font-size:15px;line-height:1.8;color:#334155;">{html.escape(draft.overview)}</p>
        <div style="margin-top:18px;">{keywords}</div>
      </div>
      <div style="margin-top:18px;padding:20px 22px;border-radius:18px;background:#ffffff;box-shadow:0 14px 40px rgba(15,23,42,0.06);">
        <h2 style="margin:0 0 16px;font-size:20px;color:#0f172a;">今日重点</h2>
        {lead_items}
      </div>
      <div style="margin-top:18px;padding:20px 22px;border-radius:18px;background:#ffffff;box-shadow:0 14px 40px rgba(15,23,42,0.06);">
        <h2 style="margin:0 0 16px;font-size:20px;color:#0f172a;">新闻速览</h2>
        {brief_items}
      </div>
      {watch_section}
      <div style="margin-top:18px;padding:14px 18px;border-radius:16px;background:#eaf1ff;color:#334155;font-size:12px;line-height:1.8;">
        生成时间：{html.escape(_format_generated_at(generated_at))}<br>
        说明：本邮件由自动化编辑流程生成，供晨间速览参考。
      </div>
    </div>
  </body>
</html>"""


def _render_html_item(item, lead: bool) -> str:
    title_size = "20px" if lead else "17px"
    summary_size = "15px" if lead else "14px"
    summary_html = ""
    if item.summary:
        summary_html = (
            f'<div style="margin-top:10px;font-size:{summary_size};line-height:1.9;color:#334155;">'
            f"{html.escape(item.summary)}</div>"
        )
    link_html = (
        f'<a href="{html.escape(item.link)}" style="color:#2563eb;text-decoration:none;font-weight:600;">原文链接</a>'
    )
    if item.domestic_reference_url:
        link_html += (
            f'<span style="color:#94a3b8;padding:0 8px;">|</span>'
            f'<a href="{html.escape(item.domestic_reference_url)}" '
            f'style="color:#0f766e;text-decoration:none;font-weight:600;">国内参考'
        )
        if item.domestic_reference_name:
            link_html += f"（{html.escape(item.domestic_reference_name)}）"
        link_html += "</a>"
    return f"""
      <div style="padding:18px 0;border-top:1px solid #e5e7eb;">
        <div style="margin-bottom:8px;">
          <span style="display:inline-block;padding:4px 8px;border-radius:999px;background:#f1f5f9;color:#475569;font-size:12px;">{html.escape(item.category)}</span>
        </div>
        <div style="font-size:{title_size};font-weight:700;line-height:1.6;color:#0f172a;">{html.escape(_display_title(item.title, item.source_name))}</div>
        {summary_html}
        <div style="margin-top:10px;">{link_html}</div>
      </div>"""


def render_text(draft: NewsletterDraft, generated_at: datetime) -> str:
    lines = [draft.subject, "", "今日主线", draft.overview, ""]
    if draft.keywords:
        lines.append("关键词：" + " / ".join(draft.keywords))
        lines.append("")
    lines.append("今日重点")
    for item in draft.lead_items:
        lines.extend(
            [
                f"- [{item.category}] {_display_title(item.title, item.source_name)}",
                f"  摘要：{item.summary}",
                f"  原文：{item.link}",
            ]
        )
        if item.domestic_reference_url:
            label = item.domestic_reference_name or "国内参考"
            lines.append(f"  国内参考（{label}）：{item.domestic_reference_url}")
    lines.append("")
    lines.append("新闻速览")
    for item in draft.brief_items:
        lines.extend(
            [
                f"- [{item.category}] {_display_title(item.title, item.source_name)}",
                f"  摘要：{item.summary}",
                f"  原文：{item.link}",
            ]
        )
        if item.domestic_reference_url:
            label = item.domestic_reference_name or "国内参考"
            lines.append(f"  国内参考（{label}）：{item.domestic_reference_url}")
    if draft.watch_items:
        lines.append("")
        lines.append("今日关注点")
        for item in draft.watch_items:
            lines.append(f"- {item}")
    lines.append("")
    lines.append("生成时间：" + _format_generated_at(generated_at))
    return "\n".join(lines)


def _display_title(title: str, source_name: str) -> str:
    clean_title = title.strip()
    clean_source = source_name.strip()
    if not clean_source:
        return clean_title
    if clean_source in clean_title:
        return clean_title
    return f"{clean_title}【{clean_source}】"


def _format_generated_at(generated_at: datetime) -> str:
    return generated_at.astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S 北京时间")
