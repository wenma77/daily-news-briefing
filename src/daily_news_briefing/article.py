from __future__ import annotations

import base64
import json
import re
import ssl
import urllib.request
from functools import lru_cache
from urllib.parse import urlencode, urlparse

from .utils import normalize_space, remove_html_noise, strip_html, truncate_text

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

OFFICIAL_DOMAIN_SUFFIXES = {
    "gov.cn",
    "news.cn",
    "xinhuanet.com",
    "cctv.com",
    "people.com.cn",
    "mofcom.gov.cn",
    "miit.gov.cn",
    "pbc.gov.cn",
    "samr.gov.cn",
    "mem.gov.cn",
    "nhc.gov.cn",
    "moe.gov.cn",
    "mot.gov.cn",
    "mohurd.gov.cn",
    "stats.gov.cn",
}

NOISE_LINE_KEYWORDS = {
    "术语表",
    "网站地图",
    "无障碍浏览",
    "当前位置",
    "专题专栏",
    "通知公告",
    "政务公开",
    "政务服务",
    "办事服务",
    "互动交流",
    "版权所有",
    "网站标识码",
    "ICP备",
    "主办单位",
    "承办单位",
    "联系我们",
    "返回顶部",
    "打印本页",
    "关闭窗口",
    "扫一扫在手机打开当前页",
    "分享到",
    "字体：",
    "来源：",
    "中国政府网",
    "宣传活动",
    "教育周",
}

OFFICIAL_PROPAGANDA_KEYWORDS = {
    "活力",
    "未来之城",
    "学习教育",
    "读书班",
    "党组",
    "工作会议",
    "活动举行",
    "成功举办",
    "筹备工作",
    "质控中心",
    "安全教育周",
    "专项招生",
    "保出行",
    "气象服务",
    "友好合作",
    "重要纽带",
    "共同发展",
    "电视电话会议",
    "工作部署",
    "组织开展",
}

OFFICIAL_HARD_INFO_HINTS = {
    "事故",
    "灾害",
    "死亡",
    "遇难",
    "受伤",
    "伤亡",
    "爆炸",
    "处罚",
    "通报",
    "挂牌督办",
    "停火",
    "关税",
    "制裁",
    "收储",
    "生效",
    "签约",
    "停运",
    "停航",
    "召回",
    "问责",
}

P_TAG_RE = re.compile(r"(?is)<p\b[^>]*>(.*?)</p>")
LI_TAG_RE = re.compile(r"(?is)<li\b[^>]*>(.*?)</li>")
GOOGLE_NEWS_ID_RE = re.compile(r"/(?:rss/)?articles/([^/?#]+)")
GOOGLE_NEWS_SIGNATURE_RE = re.compile(r'data-n-a-sg="([^"]+)"')
GOOGLE_NEWS_TIMESTAMP_RE = re.compile(r'data-n-a-ts="([^"]+)"')


def _extract_candidate_block(html_text: str) -> str:
    patterns = [
        r"(?is)<article\b[^>]*>(.*?)</article>",
        r"(?is)<main\b[^>]*>(.*?)</main>",
        r"(?is)<body\b[^>]*>(.*?)</body>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text)
        if match:
            return match.group(1)
    return html_text


def _clean_lines(text: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in re.split(r"[\r\n]+", text):
        line = normalize_space(raw_line)
        if len(line) < 20:
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return " ".join(lines)


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _is_google_news_url(url: str) -> bool:
    domain = _domain(url)
    return domain == "news.google.com" or domain.endswith(".news.google.com")


def _extract_google_news_article_id(url: str) -> str:
    match = GOOGLE_NEWS_ID_RE.search(urlparse(url).path)
    return match.group(1).strip() if match else ""


def _decode_google_news_binary_url(article_id: str) -> str:
    if not article_id:
        return ""
    try:
        decoded = base64.urlsafe_b64decode(article_id + "===")
    except Exception:
        return ""
    if decoded.startswith(b"\x08\x13\x22"):
        decoded = decoded[3:]
    if decoded.endswith(b"\xd2\x01\x00"):
        decoded = decoded[:-3]
    if not decoded:
        return ""
    length = 0
    shift = 0
    index = 0
    while index < len(decoded):
        byte = decoded[index]
        length |= (byte & 0x7F) << shift
        index += 1
        if not byte & 0x80:
            break
        shift += 7
    decoded = decoded[index:]
    candidate = decoded[:length].decode("utf-8", errors="ignore").strip()
    if candidate.startswith(("http://", "https://")):
        return candidate
    return candidate


def _fetch_google_news_metadata(url: str, timeout: int) -> tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        html_text = response.read().decode("utf-8", errors="ignore")
    signature_match = GOOGLE_NEWS_SIGNATURE_RE.search(html_text)
    timestamp_match = GOOGLE_NEWS_TIMESTAMP_RE.search(html_text)
    if not signature_match or not timestamp_match:
        return "", ""
    return timestamp_match.group(1).strip(), signature_match.group(1).strip()


def _fetch_google_news_decoded_url(article_id: str, timestamp: str, signature: str, timeout: int) -> str:
    article_request = [
        "Fbv4je",
        (
            f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
            f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{article_id}",{timestamp},"{signature}"]'
        ),
    ]
    payload = urlencode({"f.req": json.dumps([[article_request]])}).encode()
    request = urllib.request.Request(
        "https://news.google.com/_/DotsSplashUi/data/batchexecute",
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Referer": "https://news.google.com/",
            "User-Agent": USER_AGENT,
        },
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        text = response.read().decode("utf-8", errors="ignore")
    parts = text.split("\n\n", 1)
    if len(parts) < 2:
        return ""
    try:
        payload_data = json.loads(parts[1])
        inner = json.loads(payload_data[0][2])
    except Exception:
        return ""
    if len(inner) >= 2 and str(inner[1]).startswith(("http://", "https://")):
        return str(inner[1]).strip()
    return ""


@lru_cache(maxsize=512)
def resolve_google_news_url(url: str, timeout: int = 15) -> str:
    if not _is_google_news_url(url):
        return url
    article_id = _extract_google_news_article_id(url)
    if not article_id:
        return url
    decoded = _decode_google_news_binary_url(article_id)
    if decoded.startswith(("http://", "https://")):
        return decoded
    if not decoded.startswith("AU_yqL"):
        return url
    try:
        timestamp, signature = _fetch_google_news_metadata(url, timeout)
    except Exception:
        return url
    if not timestamp or not signature:
        return url
    try:
        resolved = _fetch_google_news_decoded_url(article_id, timestamp, signature, timeout)
    except Exception:
        return url
    return resolved or url


def _is_official_domain(url: str) -> bool:
    domain = _domain(url)
    return any(domain == suffix or domain.endswith(f".{suffix}") for suffix in OFFICIAL_DOMAIN_SUFFIXES)


def _is_noise_line(line: str, *, official: bool) -> bool:
    if any(keyword in line for keyword in NOISE_LINE_KEYWORDS):
        return True
    if official and any(keyword in line for keyword in OFFICIAL_PROPAGANDA_KEYWORDS):
        return True
    if len(line) < 10:
        return True
    return False


def _has_effective_information(line: str) -> bool:
    if any(keyword in line for keyword in OFFICIAL_HARD_INFO_HINTS):
        return True
    if re.search(r"\d", line) and any(
        keyword in line
        for keyword in {
            "通报",
            "处罚",
            "关税",
            "收储",
            "事故",
            "灾害",
            "停运",
            "停航",
            "召回",
            "生效",
        }
    ):
        return True
    return False


def _extract_text_blocks(html_text: str) -> list[str]:
    blocks: list[str] = []
    for pattern in (P_TAG_RE, LI_TAG_RE):
        for match in pattern.finditer(html_text):
            text = normalize_space(strip_html(match.group(1)))
            if text:
                blocks.append(text)
    return blocks


def _clean_blocks(blocks: list[str], *, official: bool) -> str:
    results: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        if _is_noise_line(block, official=official):
            continue
        if block in seen:
            continue
        seen.add(block)
        results.append(block)
        if len(results) >= 3:
            break
    if official and results and not any(_has_effective_information(block) for block in results):
        return ""
    return " ".join(results)


def fetch_article_text(url: str, char_limit: int, timeout: int = 15) -> tuple[str, str, str]:
    resolved_input_url = resolve_google_news_url(url, timeout=timeout)
    request = urllib.request.Request(resolved_input_url, headers={"User-Agent": USER_AGENT})
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")
        raw = response.read().decode("utf-8", errors="ignore")

    if "html" not in content_type.lower() and "<html" not in raw.lower():
        return "", "feed", final_url

    official = _is_official_domain(final_url)
    cleaned_html = remove_html_noise(raw)
    paragraph_text = _clean_blocks(_extract_text_blocks(cleaned_html), official=official)
    if paragraph_text:
        return truncate_text(paragraph_text, char_limit), "article", final_url

    candidate_block = _extract_candidate_block(cleaned_html)
    text = _clean_lines(strip_html(candidate_block))
    if official and _is_noise_line(text, official=True):
        return "", "feed", final_url
    return truncate_text(text, char_limit), "article" if text else "feed", final_url
