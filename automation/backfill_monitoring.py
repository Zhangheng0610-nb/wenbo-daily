"""Backfill the fixed-source monitoring corpus from public source archives.

This is intentionally conservative.  It writes every discovered original
article into the same daily monitoring files used by the map, but only marks a
source/date as complete when the source has a stable chronological archive that
was traversed for the whole requested period.  A source with a partial archive
still contributes verified records, while its coverage remains ``partial`` so
the public map will not present an overconfident trend comparison.

The script uses only Python's standard library so it runs on Windows and macOS.
Run a preview first, then add --write:

    python automation/backfill_monitoring.py --end 2026-08-27 --days 90
    python automation/backfill_monitoring.py --end 2026-08-27 --days 90 --write
"""

from __future__ import annotations

import argparse
import email.utils
import html
import json
import re
import ssl
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener
from xml.etree import ElementTree

try:
    from automation.theme_rules import classify_themes
except ModuleNotFoundError:  # direct execution: python automation/backfill_monitoring.py
    from theme_rules import classify_themes


ROOT = Path(__file__).resolve().parents[1]
MONITORING = ROOT / "content" / "监测"
USER_AGENT = "WenboDailyArchiveBackfill/1.0 (+https://zhangheng666.top/)"
SEARCH_USER_AGENT = "WenboDailyFixedSourceScan/1.0 (+https://zhangheng666.top/)"
TZ = timezone(timedelta(hours=8))

# The monitoring panel is made up of Chinese public sources.  Codex itself may
# need a proxy to reach OpenAI, but these requests must use the local network.
# Clash Verge on this host runs in system-proxy (not TUN) mode, so a proxy-free
# opener is sufficient and does not affect the rest of Codex.
DIRECT_OPENER = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()))
# Search-engine RSS is a discovery transport for the Xinhua adapter, not a
# fixed-source origin.  Use the host's normal route here; the article links
# are still restricted to Xinhua domains before entering the map corpus.
SEARCH_OPENER = build_opener()
HTTP_FALLBACK_HOSTS = {"www.ncha.gov.cn", "www.zhongguowenwubao.com", "kaogu.cssn.cn"}

SOURCE_META = {
    "ncha": ("国家文物局", "http://www.ncha.gov.cn"),
    "cultural-relics-news": ("中国文物报", "http://www.zhongguowenwubao.com"),
    "archaeology": ("中国考古网", "http://kaogu.cssn.cn"),
    "museum-association": ("中国博物馆协会", "https://www.chinamuseum.org.cn"),
    "xinhua-wenbo": ("新华网文博", "https://www.news.cn"),
    "cctv-wenbo": ("央视网文博与央视新闻", "https://yangbo.cctv.cn"),
}

PROVINCES = (
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海", "江苏",
    "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "广西", "海南",
    "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
    "香港", "澳门", "台湾",
)

NATIONAL_WORDS = ("国家文物局", "全国", "国务院", "部际", "国际博物馆日", "行业", "规划", "标准", "指南", "通知")
NATIONAL_AUTHORITIES = ("国务院", "文化和旅游部", "国家文物局", "国家文物行政部门")
POLICY_INSTRUMENTS = ("办法", "条例", "规章", "令", "规范", "标准", "通知", "规划", "规定", "规程")
NATIONAL_SCOPE_TERMS = ("全国范围内", "适用于全国", "全国博物馆", "全国性", "在全国范围")
# Archaeological discovery is a separate rubric branch from ordinary field
# work.  These patterns require a concrete archaeological object/result, so a
# routine inspection or research visit is not promoted merely by mentioning
# an archaeological site.
ARCHAEOLOGY_DISCOVERY_PATTERNS = (
    re.compile(r"(?:新发现|发现|发掘出土|清理).{0,28}(?:遗址|墓葬|墓地|古墓|遗物|文物|遗存)"),
    re.compile(r"出土.{0,20}(?:文物|器物|遗物|遗存)"),
)
MAJOR_ARCHAEOLOGY_TERMS = (
    "重大考古发现", "重大考古成果", "全国十大考古新发现", "全国十大考古发现",
)
# Routine public programming should remain in the corpus, but it must not be
# scored like a consequential sector project merely because its title names a
# museum.  The exception terms keep policy/standards/major-special-program
# training at the existing higher rubric levels.
ROUTINE_EVENT_TERMS = (
    "培训班", "培训会", "讲座", "报名", "征集", "招募", "预告", "常规宣传",
    "文创上新", "打卡", "研学",
)
ROUTINE_EVENT_EXCEPTIONS = (
    "重大", "重要", "国家级", "全国性", "专项", "制度", "行业制度", "行业培训",
    "行业标准", "行业治理", "标准", "政策实施", "政策培训", "改革", "成果发布",
    "学术", "部令", "条例", "办法", "规章",
)
# A publication's home page can also carry general current-affairs wire copy.
# Fixed-source status is necessary but not sufficient: a record still has to
# be directly about the cultural-heritage / museum field to enter this corpus.
WENBO_TERMS = (
    "文物", "考古", "博物", "遗址", "文化遗产", "世界遗产", "石窟", "古建筑", "古墓",
    "古迹", "古城", "古村", "古籍", "古画", "出土", "发掘", "修复", "保护", "展览",
    "展出", "开馆", "廊桥", "传统村落", "历史文化", "文化遗址", "文化遗产",
)


def fetch(url: str) -> str:
    """Fetch public HTML, favouring HTTP where older government sites require it."""
    urls = [url]
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.hostname in HTTP_FALLBACK_HOSTS:
        urls.append(urlunsplit(("http", parts.netloc, parts.path, parts.query, parts.fragment)))
    failure: Exception | None = None
    raw = b""
    for target in urls:
        request = Request(target, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
        try:
            with DIRECT_OPENER.open(request, timeout=20) as response:
                raw = response.read()
            break
        except (URLError, HTTPError) as exc:
            failure = exc
    else:
        raise RuntimeError(f"{url}: {failure}") from failure
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def plain(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def links(page: str, base: str) -> Iterable[tuple[str, str]]:
    """Return visible anchor text plus an absolute URL; enough for source indexes."""
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", page, flags=re.I | re.S):
        attrs, body = match.groups()
        href = re.search(r"\bhref\s*=\s*(['\"])(.*?)\1", attrs, flags=re.I | re.S)
        if not href:
            continue
        target = html.unescape(href.group(2)).strip()
        if not target or target.lower().startswith("javascript:"):
            continue
        text = plain(body)
        if text:
            yield text, urljoin(base, target)


def in_window(day: date, start: date, end: date) -> bool:
    return start <= day <= end


def date_from_url(url: str) -> date | None:
    patterns = (
        r"/(20\d{2})/(\d{1,2})/(\d{1,2})/",
        r"/(?:20\d{4})/t(20\d{2})(\d{2})(\d{2})[_/]",
        r"/(20\d{2})(\d{2})(\d{2})/",
    )
    for pattern in patterns:
        match = re.search(pattern, url)
        if not match:
            continue
        parts = [int(value) for value in match.groups()]
        if len(parts) == 2:
            parts.append(1)
        try:
            return date(*parts)
        except ValueError:
            continue
    return None


def xinhua_url(url: str) -> str:
    """Unwrap a search-result redirect while retaining only its target URL."""
    query = parse_qs(urlsplit(url).query)
    target = (query.get("url") or [url])[0]
    return unquote(html.unescape(target)).strip()


def xinhua_host(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return (
        host == "news.cn" or host.endswith(".news.cn")
        or host == "xinhuanet.com" or host.endswith(".xinhuanet.com")
    )


def parse_search_date(value: str) -> date | None:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        parsed = None
    if parsed is not None:
        return parsed.astimezone(TZ).date() if parsed.tzinfo else parsed.date()
    return date_from_url(value)


def xinhua_domain_search(start: date, end: date) -> tuple[list[dict], list[dict]]:
    """Find recent Xinhua-domain originals missing from rolling channel pages.

    This is still part of the xinhua fixed-source adapter: only Xinhua hosts
    survive, and the normal map scope gate runs after this discovery step.
    Queries are generic policy/heritage families rather than article-specific
    title searches.  URL dates, not search-engine dates, decide the window.
    """
    queries = (
        "site:xinhuanet.com 博物馆 文化和旅游部",
        "site:xinhuanet.com 文化和旅游部 博物馆",
        "site:news.cn 博物馆 施行",
        "site:news.cn 文化和旅游部 博物馆",
        "site:xinhuanet.com 文物 考古 遗址",
        "site:news.cn 文化遗产 保护",
        "site:xinhuanet.com 博物馆 展览 藏品",
    )
    found: dict[str, dict] = {}
    audits = []
    for query in queries:
        audit = {"query": query, "success": False, "returnedResultCount": 0, "acceptedCount": 0}
        try:
            # ``cc=US`` keeps Bing's RSS response stable on this host; it does
            # not change the source boundary because the result URL is still
            # checked against the Xinhua domains below.
            search_url = "https://www.bing.com/news/search?" + urlencode({
                "q": query, "format": "rss", "cc": "US", "setlang": "zh-CN",
            })
            request = Request(search_url, headers={
                "User-Agent": SEARCH_USER_AGENT,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            })
            with SEARCH_OPENER.open(request, timeout=12) as response:
                payload = response.read()
            root = ElementTree.fromstring(payload.decode("utf-8", errors="replace"))
            items = root.findall(".//item")
            audit["success"] = True
            audit["returnedResultCount"] = len(items)
            for item in items:
                title = (item.findtext("title") or "").strip()
                target = xinhua_url((item.findtext("link") or "").strip())
                published = date_from_url(target) or parse_search_date(target)
                if not title or not target or not xinhua_host(target) or not target.endswith("/c.html"):
                    continue
                if not published or not in_window(published, start, end):
                    continue
                found[target] = candidate(
                    "xinhua-wenbo", published, title, target,
                    source_section="新华网域内近期补充检索",
                )
                audit["acceptedCount"] += 1
        except Exception as exc:
            audit["error"] = f"{type(exc).__name__}: {exc}"
        audits.append(audit)
    return list(found.values()), audits


def enrich_xinhua_context(rows: list[dict]) -> None:
    """Fetch article text for generic scope/geography/impact inference."""
    for row in rows:
        try:
            page = fetch(row["url"])
        except RuntimeError:
            continue
        context = plain(page)
        # Xinhua article pages append “related stories” after the body.  Those
        # links can mention unrelated provinces and must not influence the
        # geography of the current event.
        for marker in ("【纠错】", "责任编辑", "阅读下一篇", "相关链接"):
            context = context.split(marker, 1)[0]
        row["_contextText"] = context


def usable_article_context(row: dict) -> bool:
    """Reject search stubs, while allowing short but real Xinhua articles."""
    text = row.get("_contextText", "")
    if len(text) < 400:
        return False
    return not any(marker in text for marker in ("#sdgc", ".list-item", "搜索结果", "相关链接"))


def clean_source_title(source_id: str, title: str) -> str:
    """Keep index titles separate from dates and teaser text.

    Several Chinese Archaeology pages put the title, date and a long abstract
    inside one anchor.  The date is the reliable boundary: everything after it
    is a teaser, not part of the headline.  The final cap is only a safeguard
    for malformed or script-generated entries.
    """
    value = plain(title)
    if source_id == "archaeology":
        value = re.split(r"\s*20\d{2}-\d{2}-\d{2}\b", value, maxsplit=1)[0].strip()
    value = re.sub(r"\s+", " ", value).strip(" -|｜")
    if len(value) > 120:
        cut = max((value.rfind(mark, 30, 120) for mark in "：:，,。；;——"), default=-1)
        value = value[:cut if cut >= 36 else 120].rstrip(" ，,：:;；") + "…"
    return value or "未命名文博报道"


def candidate(
    source_id: str,
    published: date,
    title: str,
    url: str,
    *,
    source_section: str = "",
) -> dict:
    row = {
        "sourceId": source_id,
        "date": published.isoformat(),
        "title": clean_source_title(source_id, title),
        "url": url,
    }
    if source_section:
        row["sourceSection"] = source_section
    return row


def is_wenbo_relevant(title: str) -> bool:
    return any(term in title for term in WENBO_TERMS)


def crawl_ncha(start: date, end: date) -> tuple[list[dict], bool, str]:
    base = "http://www.ncha.gov.cn/module/jslib/jquery/jpage/dataproxy.jsp"
    params = (
        "appid=1&webid=1&path=/&columnid=722&unitid=8000&webname="
        + quote("国家文物局") + "&permissiontype=0&page="
    )
    found: dict[str, dict] = {}
    oldest: date | None = None
    for page_no in range(1, 20):
        page = html.unescape(fetch(base + "?" + params + str(page_no)))
        page_rows = 0
        for text, url in links(page, base):
            if "/art/" not in url or "art_722_" not in url:
                continue
            published = date_from_url(url)
            if not published:
                continue
            page_rows += 1
            oldest = min(oldest, published) if oldest else published
            if in_window(published, start, end):
                found[url] = candidate("ncha", published, text, url, source_section="文物新闻")
        if oldest and oldest < start:
            return list(found.values()), True, "国家文物局“文物新闻”分页档案已回溯。"
        if page_rows == 0:
            break
    return list(found.values()), False, "国家文物局分页档案未能在预期页数内覆盖完整窗口。"


def crawl_cultural_relics_news(start: date, end: date) -> tuple[list[dict], bool, str]:
    base = "http://www.zhongguowenwubao.com"
    found: dict[str, dict] = {}
    # The public digital-paper URL is stable by publication date.  Request the
    # complete window in parallel rather than following the site's small
    # previous-issue widget one issue at a time.
    dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]

    def read_issue(published: date) -> tuple[date, str]:
        issue_url = base + "/DigitPager/paper/publishdate/" + published.isoformat()
        failure: RuntimeError | None = None
        for _attempt in range(3):
            try:
                return published, fetch(issue_url)
            except RuntimeError as exc:
                failure = exc
        raise failure or RuntimeError(f"{issue_url}: request failed")

    checked = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(read_issue, published) for published in dates]
        for future in as_completed(futures):
            try:
                published, page = future.result()
            except RuntimeError:
                continue
            checked += 1
            issue_date = published.isoformat()
            issue_url = base + "/DigitPager/paper/publishdate/" + issue_date
            # An unavailable date may render a shell page. Only accept links
            # whose embedded issue date matches the date we asked for.
            for text, url in links(page, issue_url):
                if "/paperDetail/" in url and f"publishdate/{issue_date}/" in url:
                    found[url] = candidate("cultural-relics-news", published, text, url)
    complete = checked == len(dates)
    note = "中国文物报逐日期数字报档案已回溯。" if complete else "中国文物报数字报有日期请求失败，当前仅计为部分回溯。"
    return list(found.values()), complete, note


def crawl_archaeology(start: date, end: date) -> tuple[list[dict], bool, str]:
    base = "http://kaogu.cssn.cn/"
    # The institute's homepage exposes several independent archive families;
    # the old crawler only visited three of them.  Include the visible
    # archaeology, institute-news, academic-activity, research-paper and
    # excavation-report sections, while retaining the same date boundary.
    sections = (
        "xwzx/kgdt/", "xwzx/skyw/", "xwzx/bszx/bsdt/", "xwzx/bszx/hzjl/",
        "xwzx/bszx/xshy/", "xsqy/kycg/jbbg/", "xsqy/kycg/xslw/",
    )
    found: dict[str, dict] = {}
    source_complete = True
    for section in sections:
        section_oldest: date | None = None
        for page_no in range(0, 80):
            suffix = "index.shtml" if page_no == 0 else f"index_{page_no}.shtml"
            url = urljoin(base, section + suffix)
            try:
                page = fetch(url)
            except RuntimeError:
                source_complete = False
                break
            rows = 0
            for text, article_url in links(page, url):
                if "/" + section not in article_url or not article_url.endswith(".shtml"):
                    continue
                published = date_from_url(article_url)
                if not published:
                    continue
                rows += 1
                section_oldest = min(section_oldest, published) if section_oldest else published
                if in_window(published, start, end):
                    found[article_url] = candidate("archaeology", published, text, article_url)
            if section_oldest and section_oldest < start:
                break
            if rows == 0:
                source_complete = False
                break
        else:
            source_complete = False
    if start == end:
        return list(found.values()), True, "已检查中国考古网当日核心栏目。"
    note = "中国考古网已回溯核心考古动态、学术活动和发掘简报栏目。"
    return list(found.values()), source_complete, note


def crawl_museum_association(start: date, end: date) -> tuple[list[dict], bool, str]:
    base = "https://www.chinamuseum.org.cn/cma/"
    found: dict[str, dict] = {}
    complete = True
    # These are the four public-facing information streams displayed by CMA.
    # id=14 uses the exhibition list, while the others use normal news lists.
    streams = ((11, "newList.html"), (12, "newList.html"), (13, "newList.html"), (14, "photoList.html"))
    for stream_id, endpoint in streams:
        stream_oldest: date | None = None
        for page_no in range(1, 80):
            url = f"{base}{endpoint}?id={stream_id}&pageIndex={page_no}"
            try:
                page = fetch(url)
            except RuntimeError:
                complete = False
                break
            rows = 0
            # Detail links and their adjacent YYYY-MM-DD span live in the same li.
            for block in re.findall(r"<li\b[^>]*>(.*?)</li>", page, flags=re.I | re.S):
                href = re.search(r"href\s*=\s*(['\"])(.*?)\1", block, flags=re.I | re.S)
                date_match = re.search(r"(20\d{2}-\d{2}-\d{2})", plain(block))
                if not href or not date_match or "detail.html" not in href.group(2):
                    continue
                text_match = re.search(r"<a\b[^>]*>(.*?)</a>", block, flags=re.I | re.S)
                title = plain(text_match.group(1)) if text_match else ""
                if not title:
                    continue
                try:
                    published = date.fromisoformat(date_match.group(1))
                except ValueError:
                    continue
                rows += 1
                stream_oldest = min(stream_oldest, published) if stream_oldest else published
                if in_window(published, start, end):
                    detail_url = urljoin(url, html.unescape(href.group(2)))
                    found[detail_url] = candidate("museum-association", published, title, detail_url)
            if stream_oldest and stream_oldest < start:
                break
            if rows == 0:
                complete = False
                break
        else:
            complete = False
    if start == end:
        return list(found.values()), True, "已检查中国博物馆协会当日公开资讯、行业资讯、公告和展览栏目。"
    note = "中国博物馆协会公开资讯、行业资讯、公告和展览档案已回溯。"
    return list(found.values()), complete, note


def crawl_xinhua(start: date, end: date) -> tuple[list[dict], bool, str]:
    # The dedicated 文博 channel is the primary feed.  The broader culture,
    # politics and home pages catch official Xinhua heritage/policy reports
    # that are not cross-posted into the dedicated channel.  This remains a
    # single Xinhua fixed-source scan; the scope gate below keeps general wire
    # copy out of the map corpus.
    feeds = (
        "https://www.news.cn/ci/wb.html",
        "https://www.news.cn/ci/",
        "https://www.news.cn/culture/cysj/index.html",
        "https://www.news.cn/culture/",
        "https://www.news.cn/politics/",
        "https://www.news.cn/culturepro/",
        "https://www.news.cn/",
        "https://www.xinhuanet.com/",
    )
    found: dict[str, dict] = {}
    checked_all = True
    for feed_url in feeds:
        try:
            page = fetch(feed_url)
        except RuntimeError:
            checked_all = False
            continue
        for text, article_url in links(page, feed_url):
            if not xinhua_host(article_url) or not article_url.endswith("/c.html"):
                continue
            published = date_from_url(article_url)
            if published and in_window(published, start, end):
                found[article_url] = candidate(
                    "xinhua-wenbo", published, text, article_url,
                    source_section="新华网公开栏目扫描",
                )
    search_rows, search_audits = xinhua_domain_search(start, end)
    for row in search_rows:
        found[row["url"]] = row
    enrich_xinhua_context(list(found.values()))
    # Domain search occasionally returns an Xinhua result stub rather than
    # the article body.  Keep rolling-feed rows, but do not let an unverified
    # stub supply geography/impact data or create a second record for the
    # same event when a substantive Xinhua page is available.
    for url, row in list(found.items()):
        if row.get("sourceSection") == "新华网域内近期补充检索" and not usable_article_context(row):
            del found[url]
    if start == end:
        search_failures = sum(not audit.get("success") for audit in search_audits)
        note = "已检查新华网文博、文化、时政及首页公开列表，并完成新华网域内近期补充检索。"
        if not checked_all:
            return list(found.values()), False, "新华网当日部分入口请求失败。"
        if search_failures:
            return list(found.values()), False, f"新华网栏目扫描完成，但域内补充检索有 {search_failures} 个查询失败。"
        return list(found.values()), True, note
    return list(found.values()), False, "新华网文博与文化频道公开页可回溯部分栏目，完整历史索引仍待补齐。"


def crawl_cctv(start: date, end: date) -> tuple[list[dict], bool, str]:
    # 央博是垂直专业入口；央视新闻频道补充那些进入全国公共议程的
    # 文博报道。两者同属中央广播电视总台，仍算同一个固定来源，避免
    # 把同一机构的两个栏目误当作两份独立证据。
    feeds = (
        "https://yangbo.cctv.cn/",
        "https://news.cctv.com/",
        "https://news.cctv.com/news/index.shtml",
        "https://news.cctv.com/news/china/index.html",
        "https://news.cctv.com/special/index.shtml",
    )
    found: dict[str, dict] = {}
    checked_all = True
    for feed_url in feeds:
        try:
            page = fetch(feed_url)
        except RuntimeError:
            checked_all = False
            continue
        for text, article_url in links(page, feed_url):
            if "cctv" not in article_url or not article_url.endswith(".shtml"):
                continue
            # 新闻频道首页的链接量很大；先按文博主题准入，避免把综合新闻
            # 混入监测库。文章出现在央视新闻网页，不等同于已播出新闻联播。
            if not is_wenbo_relevant(text):
                continue
            published = date_from_url(article_url)
            if published and in_window(published, start, end):
                found[article_url] = candidate("cctv-wenbo", published, text, article_url)
    if start == end:
        note = "已检查央视网文博与央视新闻当日公开列表。"
        return list(found.values()), checked_all, note if checked_all else "央视网当日部分入口请求失败。"
    return list(found.values()), False, "央视网文博与央视新闻公开页可回溯部分栏目，完整历史索引仍待补齐。"


CRAWLERS = (
    ("ncha", crawl_ncha),
    ("cultural-relics-news", crawl_cultural_relics_news),
    ("archaeology", crawl_archaeology),
    ("museum-association", crawl_museum_association),
    ("xinhua-wenbo", crawl_xinhua),
    ("cctv-wenbo", crawl_cctv),
)


def row_context(row: dict) -> str:
    return " ".join(
        str(row.get(key, "") or "")
        for key in ("title", "_contextText", "issuingAuthority", "applicability", "policyInstrument")
    )


def is_national_policy(row: dict) -> bool:
    text = row_context(row)
    has_authority = any(term in text for term in NATIONAL_AUTHORITIES)
    has_instrument = any(term in text for term in POLICY_INSTRUMENTS)
    has_national_scope = any(term in text for term in NATIONAL_SCOPE_TERMS)
    return has_authority and has_instrument and (has_national_scope or "部令" in text)


def is_substantive_archaeology_discovery(row: dict) -> bool:
    text = row_context(row)
    if not any(term in text for term in ("考古", "遗址", "墓葬", "墓地", "出土", "发掘")):
        return False
    return any(pattern.search(text) for pattern in ARCHAEOLOGY_DISCOVERY_PATTERNS)


def choose_location(row: dict) -> tuple[str, str, float]:
    title = str(row.get("title", "") or "")
    text = row_context(row)
    # A ministry-wide instrument takes precedence over province names that
    # happen to appear in its explanatory text.
    if is_national_policy(row):
        return "national", "", 0.92
    matched = [province for province in PROVINCES if province in title]
    if matched:
        return "province", matched[0], 0.90
    body_matched = [province for province in PROVINCES if province in text]
    if body_matched and not any(word in title for word in ("全国", "国家", "国务院")):
        return "province", body_matched[0], 0.62
    if any(word in text for word in NATIONAL_WORDS):
        return "national", "", 0.85
    return "unassigned", "", 0.0


def choose_themes(row: dict) -> list[str]:
    return classify_themes(title=row.get("title", ""), body=row.get("_contextText", ""))


def impact(row: dict) -> int:
    title = str(row.get("title", "") or "")
    text = row_context(row)
    if is_national_policy(row):
        return 90
    # Apply the routine-event floor before generic museum/exhibition signals.
    # Specific policy/standards/major-special-program context is exempt so a
    # meaningful sector intervention is not downgraded just because it contains
    # “培训”.
    if (
        any(term in title for term in ROUTINE_EVENT_TERMS)
        and not any(term in text for term in ROUTINE_EVENT_EXCEPTIONS)
    ):
        return 45
    if any(term in text for term in MAJOR_ARCHAEOLOGY_TERMS):
        return 90
    if is_substantive_archaeology_discovery(row):
        # The map rubric defines an ordinary archaeological discovery as
        # “重要”; only explicit major-national evidence reaches 90 above.
        return 80
    if any(word in title for word in ("国家", "全国", "世界遗产", "重大", "规划", "标准")):
        return 80
    if any(word in text for word in ("考古", "遗址", "展览", "博物馆", "保护")):
        return 60
    return 45


def as_record(
    row: dict,
    order: int,
    *,
    origin: str = "archive-backfill",
    run_type: str | None = None,
) -> dict:
    scope, province, confidence = choose_location(row)
    source_id = row["sourceId"]
    source_name, _origin = SOURCE_META[source_id]
    digest = re.sub(r"[^a-z0-9]", "", row["url"].lower())[-12:]
    themes = choose_themes(row)
    record = {
        "recordId": f"{'operational' if origin == 'fixed-panel-monitoring' else 'backfill'}-{row['date'].replace('-', '')}-{source_id}-{order:04d}-{digest}",
        "date": row["date"],
        "title": row["title"],
        "sources": [{"sourceId": source_id, "name": source_name, "url": row["url"]}],
        "scope": scope,
        "primaryProvince": province,
        "relatedProvinces": [],
        "locationTier": "title" if scope == "province" else ("national" if scope == "national" else "unassigned"),
        "locationConfidence": confidence,
        "themes": themes,
        "tags": themes + ([province] if province else []),
        "impact": impact(row),
        "selectedForDaily": False,
        "origin": origin,
    }
    if run_type:
        record["runType"] = run_type
    return record


def empty_day(day: date) -> dict:
    checked_at = datetime.combine(day, datetime.min.time(), tzinfo=TZ).replace(hour=12).isoformat()
    return {"version": 1, "date": day.isoformat(), "mode": "archive-backfill", "coverage": [
        {"sourceId": source_id, "mode": "archive-backfill", "status": "partial", "checkedAt": checked_at, "candidateCount": 0,
         "note": "历史回溯处理中，尚未确认完整覆盖。"}
        for source_id, _crawler in CRAWLERS
    ], "items": []}


def normalize_archaeology_backfill() -> None:
    """Repair old generated archaeology rows after parser improvements.

    Earlier runs could store a ``tYYYYMMDD`` article under the first day of
    its month and retain the index teaser as its title.  Move only generated
    archaeology observations to the URL-derived day and leave human-authored
    or baseline records untouched.
    """
    payloads = {}
    moved: dict[str, dict[str, dict]] = defaultdict(dict)
    for path in sorted(MONITORING.glob("2026-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        kept = []
        for item in payload.get("items", []):
            sources = item.get("sources") or []
            source = sources[0] if sources else {}
            url = source.get("url", "")
            if item.get("origin") != "archive-backfill" or source.get("sourceId") != "archaeology":
                kept.append(item)
                continue
            item["title"] = clean_source_title("archaeology", item.get("title", ""))
            corrected = date_from_url(url)
            target = corrected.isoformat() if corrected else item.get("date", path.stem)
            item["date"] = target
            item["recordId"] = re.sub(
                r"^backfill-\d{8}-", f"backfill-{target.replace('-', '')}-", item.get("recordId", "")
            )
            moved[target][url] = item
        payload["items"] = kept
        payloads[path.stem] = payload
    for target, rows in moved.items():
        payload = payloads.get(target)
        if not payload:
            continue
        payload["items"].extend(rows.values())
    for stem, payload in payloads.items():
        counts = defaultdict(int)
        for item in payload.get("items", []):
            for source in item.get("sources", []):
                counts[source.get("sourceId", "")] += 1
        for coverage in payload.get("coverage", []):
            coverage["candidateCount"] = counts[coverage.get("sourceId", "")]
        payload["items"] = sorted(
            payload.get("items", []),
            key=lambda value: (value.get("sources", [{}])[0].get("sourceId", ""), value.get("title", "")),
        )
        (MONITORING / f"{stem}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def scope_reason(row: dict) -> str:
    """Explain fixed-panel scope without treating a title keyword as the scope.

    The NCHA crawler knows that a row came from its dedicated 文物新闻 column,
    but that column also carries routine programme/communication notices.  Use
    that source context first, then apply a small general event-semantic gate;
    the gate is deliberately not a title special case for any one programme.
    """
    source_id = row.get("sourceId")
    title = plain(row.get("title", ""))
    if source_id == "archaeology":
        return "fixed-source-domain"
    if row.get("sourceSection") == "文物新闻":
        routine_markers = ("节目", "栏目", "播出", "开播", "纪录片", "专题片")
        programme_verbs = ("解码", "讲述", "探寻", "揭秘", "聚焦")
        if any(marker in title for marker in routine_markers) or (
            title.startswith("《") and any(verb in title for verb in programme_verbs)
        ):
            return "routine-program-communication"
        return "fixed-source-section"
    if is_wenbo_relevant(title):
        return "explicit-domain-signal"
    return ""


def allowed_backfill_row(row: dict) -> bool:
    reason = scope_reason(row)
    return bool(reason) and reason != "routine-program-communication"


def _outcome_details(value) -> dict:
    """Normalize legacy tuple outcomes and the operational audit shape."""
    if isinstance(value, dict):
        return dict(value)
    complete, note = value
    return {"complete": complete, "note": note, "status": "checked" if complete else "partial"}


def merge_write(
    start: date,
    end: date,
    rows: list[dict],
    outcomes: dict[str, dict | tuple[bool, str]],
    *,
    mode: str = "archive-backfill",
    checked_at: str | None = None,
    replay: bool = False,
) -> None:
    baseline_path = MONITORING / "baseline.json"
    baseline_urls: set[str] = set()
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        for item in baseline.get("records", []):
            for source in item.get("sources", []):
                if source.get("url"):
                    baseline_urls.add(source["url"].rstrip("/"))
    by_day: dict[str, list[dict]] = defaultdict(list)
    raw_rows = list(rows)
    rows = [row for row in raw_rows if allowed_backfill_row(row)]
    row_urls = {row["url"].rstrip("/") for row in rows}
    run_type = "replay" if mode == "operational" and replay else "live" if mode == "operational" else None
    for index, row in enumerate(sorted(rows, key=lambda value: (value["date"], value["sourceId"], value["url"])), 1):
        by_day[row["date"]].append(as_record(
            row,
            index,
            origin="fixed-panel-monitoring" if mode == "operational" else "archive-backfill",
            run_type=run_type,
        ))
    day = start
    while day <= end:
        path = MONITORING / f"{day.isoformat()}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = empty_day(day)
        payload.setdefault("version", 1)
        payload["date"] = day.isoformat()
        if mode == "operational":
            payload["mode"] = "operational"
            payload["runType"] = run_type
        else:
            # A maintenance backfill must not relabel an already recorded
            # operational observation as archive data.
            payload.setdefault("mode", "archive-backfill")
        prior_items = list(payload.get("items", []))
        existing = {}
        for item in payload.get("items", []):
            if not item.get("sources"):
                continue
            item_url = item["sources"][0].get("url", "")
            # A generated backfill observation must never duplicate the legacy
            # migration corpus.  Keep a human-authored operational item intact.
            if item.get("origin") == "archive-backfill" and item_url.rstrip("/") in baseline_urls:
                continue
            # A corrected parser may move an old generated observation to its
            # real publication date. Remove the stale copy here; the cleaned
            # row will be inserted into its new date below.
            if (
                item.get("origin") == "archive-backfill"
                or (mode == "operational" and item.get("origin") == "fixed-panel-monitoring")
            ) and item_url.rstrip("/") in row_urls:
                continue
            if item.get("origin") == "archive-backfill" and not allowed_backfill_row({
                "sourceId": source.get("sourceId", ""), "title": item.get("title", "")
            }):
                continue
            existing[item_url] = item
        for item in by_day.get(day.isoformat(), []):
            item_url = item["sources"][0]["url"]
            if item_url.rstrip("/") not in baseline_urls:
                # Refresh an earlier generated archive item so title/parser
                # improvements are applied on the next maintenance run. Keep
                # any human-authored operational observation untouched.
                prior = existing.get(item_url)
                if prior is None or prior.get("origin") == "archive-backfill":
                    existing[item_url] = item
        payload["items"] = sorted(existing.values(), key=lambda value: (value["sources"][0]["sourceId"], value["title"]))
        counts = defaultdict(int)
        for item in payload["items"]:
            for source in item.get("sources", []):
                counts[source.get("sourceId", "")] += 1
        current = {entry.get("sourceId"): entry for entry in payload.get("coverage", [])}
        refreshed = []
        historical_checked_at = datetime.combine(day, datetime.min.time(), tzinfo=TZ).replace(hour=12).isoformat()
        for source_id, _crawler in CRAWLERS:
            outcome = _outcome_details(outcomes[source_id])
            complete = bool(outcome.get("complete", outcome.get("status") not in {"failed", "parse_failed"}))
            note = outcome.get("note", "")
            outcome_status = outcome.get("status", "")
            if outcome_status in {"failed", "parse_failed"}:
                status = outcome_status
            else:
                status = "success" if complete and counts[source_id] else ("no_update" if complete else "partial")
            prior = current.get(source_id, {})
            # Historical recovery must never rewrite an explicitly operational
            # check, even when both observations have the same date or the
            # operational run recorded a partial/failed result.
            if mode != "operational" and prior.get("mode") == "operational":
                refreshed.append(dict(prior, sourceId=source_id, mode="operational"))
                continue
            # Preserve a later operational check timestamp if present.
            prior_checked = prior.get("checkedAt") or ""
            # A historical backfill is allowed to add records, but it must
            # never downgrade a later same-day live inspection.  Otherwise a
            # 90-day maintenance run could make an already-audited day look
            # partial again in the public coverage meter.
            if prior_checked > historical_checked_at and prior.get("status") in ("success", "no_update"):
                status = prior["status"]
                note = prior.get("note", "")
            row_coverage = {
                "sourceId": source_id,
                "mode": mode,
                **({"runType": run_type} if mode == "operational" else {}),
                "status": status,
                "checkedAt": (
                    checked_at if mode == "operational" and checked_at
                    else prior_checked if prior_checked > historical_checked_at else historical_checked_at
                ),
                "candidateCount": counts[source_id],
                "note": "" if complete else note,
            }
            if mode == "operational":
                detail = _outcome_details(outcomes[source_id])
                accepted_urls = {
                    candidate["sources"][0].get("url", "").rstrip("/")
                    for candidate in by_day.get(day.isoformat(), [])
                    if candidate["sources"][0].get("sourceId") == source_id
                    and candidate["sources"][0].get("url", "").rstrip("/") not in baseline_urls
                }
                accepted_this_run = len(accepted_urls)
                retained_existing = sum(
                    1 for item in payload["items"]
                    if item.get("sources", [{}])[0].get("sourceId") == source_id
                    and item.get("sources", [{}])[0].get("url", "").rstrip("/") not in accepted_urls
                    and any(
                        previous.get("sources", [{}])[0].get("url", "").rstrip("/")
                        == item.get("sources", [{}])[0].get("url", "").rstrip("/")
                        for previous in prior_items
                    )
                )
                row_coverage.update({
                    "rawCount": int(detail.get("rawCount", 0)),
                    "eligibleCount": int(detail.get("eligibleCount", 0)),
                    "acceptedThisRun": accepted_this_run,
                    "retainedExisting": retained_existing,
                    "finalItemCount": counts[source_id],
                    "duplicatesSkipped": int(detail.get("duplicatesSkipped", 0)),
                    "scanStatus": detail.get("status", "checked"),
                })
            refreshed.append(row_coverage)
        payload["coverage"] = refreshed
        if mode == "operational":
            source_audit = {}
            for source_id, _crawler in CRAWLERS:
                detail = _outcome_details(outcomes[source_id])
                accepted_urls = {
                    candidate["sources"][0].get("url", "").rstrip("/")
                    for candidate in by_day.get(day.isoformat(), [])
                    if candidate["sources"][0].get("sourceId") == source_id
                    and candidate["sources"][0].get("url", "").rstrip("/") not in baseline_urls
                }
                accepted_this_run = len(accepted_urls)
                retained_existing = sum(
                    1 for item in payload["items"]
                    if item.get("sources", [{}])[0].get("sourceId") == source_id
                    and item.get("sources", [{}])[0].get("url", "").rstrip("/") not in accepted_urls
                    and any(
                        previous.get("sources", [{}])[0].get("url", "").rstrip("/")
                        == item.get("sources", [{}])[0].get("url", "").rstrip("/")
                        for previous in prior_items
                    )
                )
                source_audit[source_id] = {
                    "rawCount": int(detail.get("rawCount", 0)),
                    "eligibleCount": int(detail.get("eligibleCount", 0)),
                    "acceptedCount": accepted_this_run,
                    "rawDiscovered": int(detail.get("rawCount", 0)),
                    "scopeQualified": int(detail.get("eligibleCount", 0)),
                    "acceptedThisRun": accepted_this_run,
                    "retainedExisting": retained_existing,
                    "finalItemCount": counts[source_id],
                    "duplicatesSkipped": int(detail.get("duplicatesSkipped", 0)),
                    "status": detail.get("status", "checked"),
                }
            payload["scanAudit"] = {
                "scanner": "automation/backfill_monitoring.py",
                "mode": "operational",
                "runType": run_type,
                "completed": True,
                "checkedAt": checked_at,
                "replay": bool(replay),
                "sources": source_audit,
            }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        day += timedelta(days=1)
    normalize_archaeology_backfill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan the fixed-source map corpus or backfill its public archives.")
    parser.add_argument("--end", type=date.fromisoformat, default=date.today(), help="inclusive end date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=90, help="number of inclusive days to backfill")
    parser.add_argument(
        "--mode", choices=("archive-backfill", "operational"), default="archive-backfill",
        help="archive recovery (default) or the formal fixed-panel daily scan",
    )
    parser.add_argument("--replay", action="store_true", help="mark an operational run as a controlled historical replay")
    parser.add_argument("--write", action="store_true", help="write merged daily monitoring files")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")
    if args.mode == "operational" and args.days != 1:
        parser.error("operational mode requires exactly one observation day")
    if args.mode != "operational" and args.replay:
        parser.error("--replay requires --mode operational")
    if args.mode == "operational" and args.end != date.today() and not args.replay:
        parser.error("historical operational dates require --replay")
    start = args.end - timedelta(days=args.days - 1)
    all_rows: list[dict] = []
    outcomes: dict[str, dict] = {}
    checked_at = datetime.now(TZ).isoformat(timespec="seconds") if args.mode == "operational" else None
    for source_id, crawler in CRAWLERS:
        try:
            rows, complete, note = crawler(start, args.end)
        except Exception as exc:  # keep one source outage from discarding other evidence
            rows, complete, note = [], False, f"固定来源扫描失败：{exc}"
            status = "failed"
        else:
            status = "checked" if complete else "partial"
        raw_count = len(rows)
        rows = list({row["url"].rstrip("/"): row for row in rows}.values())
        duplicate_count = raw_count - len(rows)
        eligible_count = sum(1 for row in rows if allowed_backfill_row(row))
        all_rows.extend(rows)
        outcomes[source_id] = {
            "complete": complete,
            "status": status,
            "note": note,
            "rawCount": raw_count,
            "eligibleCount": eligible_count,
            "duplicatesSkipped": duplicate_count,
        }
        print(f"{source_id}: 原始 {raw_count} 条，符合准入 {eligible_count} 条 | {status} | {note}")
    relevant = [row for row in all_rows if allowed_backfill_row(row)]
    print(f"合计：{len(all_rows)} 条原文候选，其中 {len(relevant)} 条符合文博主题准入，时间范围 {start} 至 {args.end}。")
    if args.write:
        merge_write(
            start, args.end, all_rows, outcomes, mode=args.mode,
            checked_at=checked_at, replay=(args.mode == "operational" and args.replay),
        )
        print(f"已合并写入 {MONITORING}。")
    else:
        print("预览模式：未写入。确认后加 --write。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
