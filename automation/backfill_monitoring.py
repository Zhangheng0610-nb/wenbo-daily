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
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
MONITORING = ROOT / "content" / "监测"
USER_AGENT = "WenboDailyArchiveBackfill/1.0 (+https://zhangheng666.top/)"
TZ = timezone(timedelta(hours=8))

# The monitoring panel is made up of Chinese public sources.  Codex itself may
# need a proxy to reach OpenAI, but these requests must use the local network.
# Clash Verge on this host runs in system-proxy (not TUN) mode, so a proxy-free
# opener is sufficient and does not affect the rest of Codex.
DIRECT_OPENER = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()))
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
THEME_WORDS = (
    ("考古", ("考古", "遗址", "发掘", "墓葬", "石窟")),
    ("文物保护", ("保护", "修复", "安全", "预防性", "古建筑")),
    ("博物馆", ("博物馆", "博物院", "纪念馆", "展馆", "开馆")),
    ("展览", ("展", "展览", "展出", "开展")),
    ("数字化", ("数字", "科技", "数据", "人工智能", "虚拟")),
    ("国际交流", ("国际", "海外", "世界遗产", "中外", "联合国")),
    ("政策行业", ("通知", "规划", "办法", "标准", "指南", "发布", "会议")),
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
        r"/(20\d{2})(\d{2})/t\d+",
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


def candidate(source_id: str, published: date, title: str, url: str) -> dict:
    return {"sourceId": source_id, "date": published.isoformat(), "title": title, "url": url}


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
                found[url] = candidate("ncha", published, text, url)
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
        return published, fetch(issue_url)

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
    sections = ("xwzx/kgdt/", "xwzx/bszx/", "xsqy/kycg/jbbg/")
    found: dict[str, dict] = {}
    source_complete = True
    for section in sections:
        section_oldest: date | None = None
        for page_no in range(0, 40):
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
        for page_no in range(1, 40):
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
    url = "https://www.news.cn/ci/wb.html"
    found: dict[str, dict] = {}
    try:
        page = fetch(url)
    except RuntimeError as exc:
        return [], False, str(exc)
    for text, article_url in links(page, url):
        if "news.cn/ci/" not in article_url or not article_url.endswith("/c.html"):
            continue
        published = date_from_url(article_url)
        if published and in_window(published, start, end):
            found[article_url] = candidate("xinhua-wenbo", published, text, article_url)
    if start == end:
        return list(found.values()), True, "已检查新华网文博当日公开列表。"
    return list(found.values()), False, "新华网文博公开页仅稳定提供近期列表，历史索引仍待补齐。"


def crawl_cctv(start: date, end: date) -> tuple[list[dict], bool, str]:
    # 央博是垂直专业入口；央视新闻频道补充那些进入全国公共议程的
    # 文博报道。两者同属中央广播电视总台，仍算同一个固定来源，避免
    # 把同一机构的两个栏目误当作两份独立证据。
    feeds = ("https://yangbo.cctv.cn/", "https://news.cctv.com/")
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


def choose_location(title: str) -> tuple[str, str, float]:
    matched = [province for province in PROVINCES if province in title]
    if matched:
        return "province", matched[0], 0.90
    if any(word in title for word in NATIONAL_WORDS):
        return "national", "", 0.85
    return "unassigned", "", 0.0


def choose_themes(title: str) -> list[str]:
    themes = [theme for theme, words in THEME_WORDS if any(word in title for word in words)]
    return themes[:3] or ["政策行业"]


def impact(title: str) -> int:
    if any(word in title for word in ("国家", "全国", "世界遗产", "重大", "规划", "标准")):
        return 80
    if any(word in title for word in ("考古", "遗址", "展览", "博物馆", "保护")):
        return 60
    return 45


def as_record(row: dict, order: int) -> dict:
    scope, province, confidence = choose_location(row["title"])
    source_id = row["sourceId"]
    source_name, _origin = SOURCE_META[source_id]
    digest = re.sub(r"[^a-z0-9]", "", row["url"].lower())[-12:]
    themes = choose_themes(row["title"])
    return {
        "recordId": f"backfill-{row['date'].replace('-', '')}-{source_id}-{order:04d}-{digest}",
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
        "impact": impact(row["title"]),
        "selectedForDaily": False,
        "origin": "archive-backfill",
    }


def empty_day(day: date) -> dict:
    checked_at = datetime.combine(day, datetime.min.time(), tzinfo=TZ).replace(hour=12).isoformat()
    return {"version": 1, "date": day.isoformat(), "coverage": [
        {"sourceId": source_id, "status": "partial", "checkedAt": checked_at, "candidateCount": 0,
         "note": "历史回溯处理中，尚未确认完整覆盖。"}
        for source_id, _crawler in CRAWLERS
    ], "items": []}


def merge_write(start: date, end: date, rows: list[dict], outcomes: dict[str, tuple[bool, str]]) -> None:
    baseline_path = MONITORING / "baseline.json"
    baseline_urls: set[str] = set()
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        for item in baseline.get("records", []):
            for source in item.get("sources", []):
                if source.get("url"):
                    baseline_urls.add(source["url"].rstrip("/"))
    by_day: dict[str, list[dict]] = defaultdict(list)
    rows = [row for row in rows if is_wenbo_relevant(row["title"])]
    for index, row in enumerate(sorted(rows, key=lambda value: (value["date"], value["sourceId"], value["url"])), 1):
        by_day[row["date"]].append(as_record(row, index))
    day = start
    while day <= end:
        path = MONITORING / f"{day.isoformat()}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = empty_day(day)
        payload.setdefault("version", 1)
        payload["date"] = day.isoformat()
        existing = {}
        for item in payload.get("items", []):
            if not item.get("sources"):
                continue
            item_url = item["sources"][0].get("url", "")
            # A generated backfill observation must never duplicate the legacy
            # migration corpus.  Keep a human-authored operational item intact.
            if item.get("origin") == "archive-backfill" and item_url.rstrip("/") in baseline_urls:
                continue
            if item.get("origin") == "archive-backfill" and not is_wenbo_relevant(item.get("title", "")):
                continue
            existing[item_url] = item
        for item in by_day.get(day.isoformat(), []):
            item_url = item["sources"][0]["url"]
            if item_url.rstrip("/") not in baseline_urls:
                existing.setdefault(item_url, item)
        payload["items"] = sorted(existing.values(), key=lambda value: (value["sources"][0]["sourceId"], value["title"]))
        counts = defaultdict(int)
        for item in payload["items"]:
            for source in item.get("sources", []):
                counts[source.get("sourceId", "")] += 1
        current = {entry.get("sourceId"): entry for entry in payload.get("coverage", [])}
        refreshed = []
        checked_at = datetime.combine(day, datetime.min.time(), tzinfo=TZ).replace(hour=12).isoformat()
        for source_id, _crawler in CRAWLERS:
            complete, note = outcomes[source_id]
            status = "success" if complete and counts[source_id] else ("no_update" if complete else "partial")
            prior = current.get(source_id, {})
            # Preserve a later operational check timestamp if present.
            prior_checked = prior.get("checkedAt", "")
            refreshed.append({
                "sourceId": source_id, "status": status,
                "checkedAt": prior_checked if prior_checked > checked_at else checked_at,
                "candidateCount": counts[source_id],
                "note": "" if complete else note,
            })
        payload["coverage"] = refreshed
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        day += timedelta(days=1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill the fixed-source map corpus from source archives.")
    parser.add_argument("--end", type=date.fromisoformat, default=date.today(), help="inclusive end date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=90, help="number of inclusive days to backfill")
    parser.add_argument("--write", action="store_true", help="write merged daily monitoring files")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")
    start = args.end - timedelta(days=args.days - 1)
    all_rows: list[dict] = []
    outcomes: dict[str, tuple[bool, str]] = {}
    for source_id, crawler in CRAWLERS:
        try:
            rows, complete, note = crawler(start, args.end)
        except Exception as exc:  # keep one source outage from discarding other evidence
            rows, complete, note = [], False, f"历史回溯请求失败：{exc}"
        rows = list({row["url"]: row for row in rows}.values())
        all_rows.extend(rows)
        outcomes[source_id] = (complete, note)
        print(f"{source_id}: {len(rows)} 条 | {'完整' if complete else '部分'} | {note}")
    relevant = [row for row in all_rows if is_wenbo_relevant(row["title"])]
    print(f"合计：{len(all_rows)} 条原文候选，其中 {len(relevant)} 条符合文博主题准入，时间范围 {start} 至 {args.end}。")
    if args.write:
        merge_write(start, args.end, all_rows, outcomes)
        print(f"已合并写入 {MONITORING}。")
    else:
        print("预览模式：未写入。确认后加 --write。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
