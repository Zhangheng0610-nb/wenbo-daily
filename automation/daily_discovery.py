"""Auditable broad discovery helpers for the daily editorial report.

The map's fixed six-source monitoring remains separate.  This module records
the wider discovery pass used by the daily editor: source-driven scans,
real query-driven RSS searches, and lightweight event-level deduplication.  It
deliberately does not decide what should be published.
"""
from __future__ import annotations

import argparse
import email.utils
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlsplit
from urllib.request import Request, build_opener
from xml.etree import ElementTree

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[1]

from automation.backfill_monitoring import fetch, links
from automation.governance import canonical_url, source_info

TZ = timezone(timedelta(hours=8))
DISCOVERY_DIR = ROOT / "content" / "发现"
# Search endpoints are public web services and may require the host's normal
# HTTP route.  Fixed-source monitoring keeps its proxy-free opener separately;
# broad discovery must not silently use that network policy.
SEARCH_OPENER = build_opener()
SEARCH_USER_AGENT = "WenboDailyDiscovery/1.1 (+https://zhangheng666.top/)"

# These are repeatable source-driven entry points, not additions to the map
# panel.  A scan can fail independently and must never be recorded as
# ``no_update``.
SOURCE_SCANS = (
    {
        "sourceId": "ncha-wenwu-news",
        "name": "国家文物局文物新闻栏目",
        "kind": "source_scan",
        "scope": "domestic",
        "url": "http://www.ncha.gov.cn/module/jslib/jquery/jpage/dataproxy.jsp?appid=1&webid=1&path=/&columnid=722&unitid=8000&webname=" + quote("国家文物局") + "&permissiontype=0&page=1",
        "domain": "ncha.gov.cn",
    },
    {
        "sourceId": "ncha-policy-news",
        "name": "国家文物局政策/工作动态栏目",
        "kind": "source_scan",
        "scope": "domestic",
        "url": "http://www.ncha.gov.cn/module/jslib/jquery/jpage/dataproxy.jsp?appid=1&webid=1&path=/&columnid=1879&unitid=8000&webname=" + quote("国家文物局") + "&permissiontype=0&page=1",
        "domain": "ncha.gov.cn",
    },
    {
        "sourceId": "xinhua-cultural",
        "name": "新华网文化/文博栏目",
        "kind": "source_scan",
        "scope": "domestic",
        "url": "https://www.news.cn/ci/wb.html",
        "domain": "news.cn",
    },
    {
        "sourceId": "chinanews-cultural",
        "name": "中国新闻网文化栏目",
        "kind": "source_scan",
        "scope": "domestic",
        "url": "https://www.chinanews.com.cn/cul/",
        "domain": "chinanews.com.cn",
    },
    {
        "sourceId": "unesco-news",
        "name": "UNESCO新闻",
        "kind": "source_scan",
        "scope": "international",
        "url": "https://www.unesco.org/en/newsroom/news",
        "domain": "unesco.org",
    },
    {
        "sourceId": "archaeology-magazine",
        "name": "Archaeology Magazine新闻",
        "kind": "source_scan",
        "scope": "international",
        "url": "https://archaeology.org/news/",
        "domain": "archaeology.org",
    },
)

QUERY_FAMILIES = (
    {"id": "policy-governance", "scope": "domestic", "queries": ("文物 政策 管理办法 通知 施行", "博物馆 管理 政策 文物局", "site:gov.cn 文物 博物馆 政策")},
    {"id": "archaeology-heritage", "scope": "domestic", "queries": ("考古 新发现 遗址 保护 研究成果", "文物保护 工程 遗产 条例", "site:chinanews.com.cn 考古 遗址 文明", "site:henandaily.cn 考古 文物")},
    {"id": "museum-public-culture", "scope": "domestic", "queries": ("博物馆 开馆 展览 重要馆藏 官方", "博物馆 安全 声明 重大事件", "site:thepaper.cn 博物馆 文物 安全", "site:gov.cn 博物馆 开馆 展览", "博物馆 展览 闭幕 参观人次", "博物馆 国际合作 文物展 数字展示", "site:chinanews.com.cn 博物馆 展览")},
    {"id": "digital-heritage", "scope": "domestic", "queries": ("数字文博 AI 三维 虚拟现实 博物馆", "文物 数字化 数据平台 保护")},
    {"id": "international-heritage", "scope": "international", "queries": ("museum archaeology cultural heritage", "archaeological discovery heritage site", "heritage protection museum theft", "repatriation museum policy", "digital heritage museum technology", "site:polizei.gv.at museum theft", "site:aa.com.tr archaeology heritage", "site:reuters.com museum archaeology heritage", "site:apnews.com museum archaeology heritage")},
)

QUERY_BACKENDS = (
    {"id": "bing-news-rss", "name": "Bing News RSS", "base": "https://www.bing.com/news/search", "locale": "zh"},
    {"id": "google-news-rss", "name": "Google News RSS", "base": "https://news.google.com/rss/search", "locale": "en"},
)

GENERIC_TITLE_WORDS = {
    "文物", "博物馆", "考古", "文化", "遗址", "发布", "举行", "召开", "相关", "我国", "中国", "国际",
    "正式", "工作", "活动", "项目", "新闻", "报道", "最新", "举行", "开展", "推出", "举办",
}
GENERIC_EVENT_WORDS = {
    "museum", "museums", "archaeology", "archaeological", "heritage", "cultural", "culture", "art",
    "news", "report", "official", "china", "chinese", "international", "new", "found", "finds",
    "discovered", "discovery", "research", "study", "event", "theft", "stolen", "steal", "thieves",
    "from", "with", "before", "in", "the", "of", "and", "to", "a", "an", "on", "for", "buy", "tickets",
    "plundering", "brazen", "daytime", "heist",
}
EVIDENCE_CONTEXT_TERMS = {
    "发布", "公布", "举行", "召开", "开展", "推出", "举办", "正式", "相关", "活动", "工作", "成果", "研究",
    "落幕", "闭幕", "开幕", "开馆", "开放", "展期", "接待访客逾", "万人次", "个半月逾", "万访客",
    "文创商品收入逾", "万元", "official", "source", "news", "report",
}
EVIDENCE_CONTEXT_PATTERNS = re.compile(r"(?:接待|访客|人次|收入|万元|带来|逾|超|展期|文创|落幕|闭幕|开幕|开馆|正式)")
DEVELOPMENT_WORDS = ("正式施行", "正式开幕", "正式开放", "揭牌", "签约", "完成交接", "追回", "落网", "发布结论", "新发现", "新增", "启动发掘", "落地")
EVENT_KIND_TERMS = {
    "policy": ("办法", "条例", "规章", "规划", "施行", "规范", "制度"),
    "archaeology": ("考古", "遗址", "墓", "发掘", "出土", "发现", "研究"),
    "museum": ("博物馆", "展览", "大展", "特展", "开馆", "开幕", "闭幕", "展期", "访客"),
    "security": ("盗窃", "失窃", "抢劫", "安全", "追回", "受损"),
    "heritage": ("世界遗产", "历史文化名城", "文化遗产", "古城", "古村"),
    "cooperation": ("合作", "联合", "签约", "备忘录", "交流"),
}
EVENT_ENTITY_SUFFIXES = (
    "展示馆", "博物馆", "博物院", "纪念馆", "研究所", "考古所", "遗址群", "遗址", "大展", "展览",
    "文物展", "墓地", "古墓", "岩画", "古城", "保护工程", "数据平台", "数据库", "资源库", "项目",
)
EVENT_ACTION_PATTERNS = (
    ("policy", ("管理办法", "实施办法", "保护条例", "条例", "规章", "规划", "规范", "制度", "部令")),
    ("security", ("盗窃", "失窃", "抢劫", "被盗", "追回", "落网", "安全事件", "安全事故")),
    ("archaeology", ("考古发掘", "发掘成果", "遗址调查", "考古发现", "新发现", "出土", "研究揭示", "成果公布")),
    ("opening", ("开馆", "开幕", "正式开放", "启用", "落成", "揭牌")),
    ("exhibition", ("展览", "大展", "特展", "展期", "落幕", "闭幕")),
    ("digital_resource", ("数据库", "数据平台", "资源库", "数字资源", "数字化项目")),
    ("cooperation", ("联合考古", "签约", "合作", "备忘录", "交接")),
)
HIGH_VALUE_TERMS = (
    "政策", "办法", "条例", "施行", "规范", "改革", "考古", "发掘", "新发现", "遗址", "遗产保护", "保护工程",
    "保护研究", "研究成果", "研究揭示", "成果公布", "揭牌", "合作", "签约", "联合考古", "藏品", "安全", "盗窃", "追回", "调查结论", "总结会", "国家历史文化名城", "历史文化名城",
    "museum policy", "museum theft", "stolen", "repatriation", "archaeological discovery", "archaeologists",
    "heritage protection", "conservation", "excavation", "unearthed", "new discovery", "research findings",
)
ROUTINE_TERMS = ("报名", "招募", "研学", "常规讲座", "讲座预告", "市集", "音乐季", "周末活动", "打卡", "优惠", "routine", "workshop", "weekend events")
RELEVANCE_TERMS = (
    "文物", "博物馆", "考古", "遗址", "文化遗产", "世界遗产", "国家历史文化名城", "历史文化名城", "石窟", "古建筑", "古墓", "古迹", "发掘", "出土",
    "展览", "大展", "特展", "临展", "联展", "展期", "藏品", "标本", "保护", "修复", "博物馆", "museum", "archaeology", "heritage", "conservation", "excavation",
)

# Editorial importance is deliberately independent from source tier.  These
# rules only prioritize the order in which a human/Codex editor should try to
# upgrade evidence; they do not publish a record or replace the evidence gate.
POLICY_PRIORITY_TERMS = ("办法", "条例", "规章", "规划", "规范", "正式施行", "部令", "制度")
NATIONAL_POLICY_TERMS = ("国家文物局", "文化和旅游部", "全国范围", "全国博物馆", "国家级")
ARCHAEOLOGY_DISCOVERY_TERMS = ("考古发现", "考古发掘", "发掘成果", "成果公布", "研究揭示", "研究成果", "新发现", "新认识", "出土", "墓地发现", "遗址发现")
MAJOR_DISCOVERY_TERMS = ("重大考古", "重大新发现", "填补", "重要发现", "重大发现")
SECURITY_PRIORITY_TERMS = ("盗窃", "失窃", "抢劫", "文物安全事件", "追回", "落网", "藏品受损")
REPATRIATION_TERMS = ("文物返还", "文物追索", "归还", "交接完成")
HERITAGE_RECOGNITION_TERMS = ("世界遗产", "国家历史文化名城", "历史文化名城")
MUSEUM_PROJECT_TERMS = ("重要展览", "大型展览", "大展", "特展", "正式开幕", "正式开放", "闭幕", "开馆")
MUSEUM_SCALE_TERMS = ("访客", "人次", "观众", "参观人数", "展期")
DIGITAL_PRIORITY_TERMS = ("数字化", "人工智能", "三维扫描", "三维建模", "数字孪生", "数据库", "数据平台", "智慧博物馆", "虚拟现实", "增强现实")
COOPERATION_TERMS = ("联合考古", "国际合作", "合作签约", "签约", "合作备忘录", "国际交流")
ROUTINE_PRIORITY_TERMS = ROUTINE_TERMS + ("培训", "开班", "常规会议", "一般会议", "普通活动", "探馆", "参观", "消费体验")


def now_cn() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def parse_date(value: str) -> date | None:
    text = value or ""
    patterns = (
        r"(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)",
        r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)",
        r"(?<!\d)(20\d{2})年(\d{1,2})月(\d{1,2})日",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            return date(*(int(part) for part in match.groups()))
        except ValueError:
            continue
    return None


def parse_feed_date(value: str) -> date | None:
    """Parse RSS publication dates without treating an unparseable result as current."""
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        parsed = None
    if parsed is not None:
        return parsed.astimezone(TZ).date() if parsed.tzinfo else parsed.date()
    return parse_date(value)


def actual_query(query: str, start: date, end: date) -> str:
    """Make the requested date window explicit in every real search."""
    return f'{query} after:{start.isoformat()} before:{(end + timedelta(days=1)).isoformat()}'


def search_url(backend: dict, query: str, scope: str = "international") -> str:
    if backend["id"] == "bing-news-rss":
        return backend["base"] + "?" + urlencode({"q": query, "format": "rss"})
    if scope == "domestic":
        params = {"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return backend["base"] + "?" + urlencode(params)


def parse_rss(xml_text: str, *, family: dict, backend: dict, query: str, start: date, end: date) -> tuple[list[dict], int, int]:
    root = ElementTree.fromstring(xml_text)
    records = []
    returned = 0
    undated = 0
    for item in root.findall(".//item"):
        returned += 1
        def value(tag: str) -> str:
            node = item.find(tag)
            return (node.text or "").strip() if node is not None else ""
        title = value("title")
        url = value("link")
        published = parse_feed_date(value("pubDate"))
        if not published:
            undated += 1
            continue
        if not (start <= published <= end):
            continue
        source = item.find("source")
        source_name = (source.text or "").strip() if source is not None else backend["name"]
        record = {
            "title": title,
            "publishedDate": published.isoformat(),
            "url": url,
            "discoveredVia": backend["id"],
            "discoverySourceType": "query_search",
            "discoveryQuery": query,
            "queryFamily": family["id"],
            "queryBackend": backend["id"],
            "scope": family["scope"],
            "sourceDomain": source_name,
        }
        records.append(record)
    return records, returned, undated


def _execute_one_query(family: dict, backend: dict, base_query: str, start: date, end: date, *, date_filter: bool = True) -> tuple[list[dict], dict]:
    query = actual_query(base_query, start, end) if date_filter else base_query
    audit = {
        "queryFamily": family["id"],
        "scope": family["scope"],
        "backend": backend["id"],
        "actualQuery": query,
        "executedAt": now_cn(),
        "success": False,
        "failure": None,
        "returnedResultCount": 0,
        "acceptedRawCount": 0,
        "undatedResultCount": 0,
        "dateFilterApplied": date_filter,
    }
    try:
        request = Request(search_url(backend, query, family["scope"]), headers={
            "User-Agent": SEARCH_USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        with SEARCH_OPENER.open(request, timeout=8) as response:
            payload = response.read()
        found, returned, undated = parse_rss(
            payload.decode("utf-8", errors="replace"), family=family, backend=backend,
            query=query, start=start, end=end
        )
        audit["success"] = True
        audit["returnedResultCount"] = returned
        audit["acceptedRawCount"] = len(found)
        audit["undatedResultCount"] = undated
        return found, audit
    except Exception as exc:  # each query is independently auditable
        audit["failure"] = f"{type(exc).__name__}: {exc}"
        return [], audit


def execute_queries(required_date: date, start: date, end: date) -> tuple[list[dict], list[dict]]:
    """Execute every configured query concurrently, retaining one audit row per query."""
    tasks = [
        (family, backend, base_query)
        for family in QUERY_FAMILIES
        for backend in QUERY_BACKENDS
        for base_query in family["queries"]
    ]
    results = [None] * len(tasks)
    with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as pool:
        futures = {
            pool.submit(_execute_one_query, family, backend, base_query, start, end): index
            for index, (family, backend, base_query) in enumerate(tasks)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    records = []
    audits = []
    for found, audit in results:
        records.extend(found)
        audits.append(audit)
    return records, audits


def compact(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())


def meaningful_terms(text: str) -> set[str]:
    terms = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]+", (text or "").lower()))
    return {term for term in terms if term not in GENERIC_TITLE_WORDS and len(term) >= 2}


def clean_discovery_title(title: str) -> str:
    """Remove transport/source suffixes before comparing syndicated reports."""
    value = re.sub(r"\s+[-|｜]\s+[^-—|｜]+$", "", title or "").strip()
    return re.sub(r"^[\s【\[]*(?:新华社|中新网|央视网|媒体报道)[：:）)、 ]*", "", value).strip()


def event_kind(title: str) -> set[str]:
    text = clean_discovery_title(title)
    return {kind for kind, terms in EVENT_KIND_TERMS.items() if any(term in text for term in terms)}


def event_action(text: str) -> str:
    """Return a coarse event action so one entity's different events stay separate."""
    value = text or ""
    for action, patterns in EVENT_ACTION_PATTERNS:
        if any(pattern in value for pattern in patterns):
            return action
    return ""


def event_named_entity(text: str) -> str:
    """Extract a named institution/project/instrument, not a generic topic word."""
    value = clean_discovery_title(text)
    quoted = re.findall(r"《([^》]{2,48})》", value)
    for phrase in quoted:
        if any(phrase.endswith(suffix) for suffix in EVENT_ENTITY_SUFFIXES) or any(
            phrase.endswith(suffix) for suffix in ("办法", "条例", "规章", "规划", "规范")
        ):
            return compact(phrase)
    candidates = []
    for suffix in EVENT_ENTITY_SUFFIXES:
        for candidate in re.findall(rf"[\u4e00-\u9fff]{{4,40}}{re.escape(suffix)}", value):
            # A body sentence can continue with the host institution, e.g.
            # “成果展示馆在湖南省博物馆开馆”.  Keep the named object before
            # the relation rather than accidentally choosing the host venue.
            candidate = re.split(r"(?:在|于|与|和|并|发布|推出|位于)", candidate, maxsplit=1)[0]
            if len(candidate) >= 4:
                candidates.append(candidate)
    if not candidates:
        return ""
    # Prefer the longest named phrase; this keeps a specific project ahead of
    # a hosting institution such as 湖南省博物馆.
    return compact(max(candidates, key=len))


def canonical_event_identity(record: dict) -> str:
    """Build a stable cross-report identity from entity + action + structure.

    Published daily Markdown is the historical authority.  Its body is used
    here so a shortened later headline can still match the same event without
    treating a same-institution, different-action event as a duplicate.
    """
    identity_hint = record.get("canonicalIdentity")
    if identity_hint:
        return str(identity_hint)
    explicit = record.get("canonicalEventId")
    if explicit:
        return str(explicit)
    title = str(record.get("title") or "")
    context = " ".join(
        str(record.get(key) or "")
        for key in ("summary", "body", "notes", "institution", "publisher", "entity", "eventType", "location")
    )
    # Headline entities are preferred over descriptive phrases in the body
    # (for example “首座以语言资源为主题的展示馆”).
    named = event_named_entity(title) or event_named_entity(context)
    text = " ".join((title, context))
    action = event_action(text)
    if named and action:
        location = compact(str(record.get("location") or ""))
        return "named|" + named + "|" + action + ("|" + location if location else "")
    structured = [record.get("entity", ""), record.get("eventType", ""), record.get("location", "")]
    if any(structured):
        return "structured|" + "|".join(compact(str(bit)) for bit in structured)
    if named:
        return "named|" + named
    return ""


def event_report_relation(current: dict, previous: dict) -> tuple[str, str] | None:
    """Find same-event reports without treating similar subjects as one event."""
    current_url = canonical_url(current.get("url") or "")
    previous_url = canonical_url(previous.get("url") or "")
    if current_url and previous_url and current_url == previous_url:
        return ("same_day_duplicate" if current.get("publishedDate") == previous.get("publishedDate") else "historical_duplicate", "same canonical discovery URL")
    current_identity = canonical_event_identity(current)
    previous_identity = canonical_event_identity(previous)
    if current_identity and current_identity == previous_identity:
        if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
            return ("new_development", "same canonical event identity with a substantive development marker")
        return ("same_day_duplicate" if current.get("publishedDate") == previous.get("publishedDate") else "historical_duplicate", "same canonical event identity")
    left = meaningful_terms(clean_discovery_title(current.get("title", "")))
    right = meaningful_terms(clean_discovery_title(previous.get("title", "")))
    shared = left & right
    generic_cjk = set(GENERIC_TITLE_WORDS) | {
        "大展", "展览", "展", "开展", "展在", "政策", "政策解读", "政策措施", "办法", "管理办法", "实施办法", "规划", "十五五", "征求意见", "意见", "公告",
        "会议", "活动", "研究成果", "新发现", "考古发现", "博物馆", "美术馆", "文物", "考古", "遗址", "发现", "成果", "研究", "文化", "遗产", "国际", "中国", "国家",
    }
    anchors = {
        term for term in shared
        if len(term) >= 4
        and term not in GENERIC_EVENT_WORDS
        and not re.fullmatch(r"[a-z0-9.]+", term)
        and not any(generic in term for generic in generic_cjk)
    }
    # A title may shorten a named event, such as "古埃及文明大展" versus
    # "古埃及展". Accept a shared non-generic CJK name fragment while keeping
    # broad words such as 博物馆/政策 out of event identity matching.
    left_cjk = [term for term in left if re.search(r"[\u4e00-\u9fff]", term)]
    right_cjk = [term for term in right if re.search(r"[\u4e00-\u9fff]", term)]
    for lterm in left_cjk:
        for rterm in right_cjk:
            fragment = lterm if len(lterm) <= len(rterm) and lterm in rterm else rterm if rterm in lterm else ""
            if len(fragment) >= 3 and not any(generic in fragment for generic in generic_cjk):
                anchors.add(fragment)
    # Continuous Chinese titles are often not segmented around a shortened
    # exhibition name. A three-character fragment is accepted only when both
    # titles visibly describe an exhibition, avoiding generic policy or
    # archaeology fragments such as 管理办法/址考古.
    left_text = "".join(left_cjk)
    right_text = "".join(right_cjk)
    for size in (3,):
        for start in range(0, len(left_text) - size + 1):
            fragment = left_text[start:start + size]
            if fragment in right_text and not any(generic in fragment for generic in generic_cjk):
                left_pos = left_text.find("展", start, min(len(left_text), start + size + 7))
                right_pos = right_text.find("展")
                if left_pos < 0 or right_pos < 0 or abs(left_pos - start) > 6 or abs(right_pos - right_text.find(fragment)) > 6:
                    continue
                anchors.add(fragment)
                break
    if not anchors or not (event_kind(current.get("title", "")) & event_kind(previous.get("title", ""))):
        return None
    try:
        distance = abs(date.fromisoformat(current.get("publishedDate", "")) - date.fromisoformat(previous.get("publishedDate", ""))).days
    except (TypeError, ValueError):
        distance = 99
    if distance > 2 and len(shared) < 2:
        return None
    if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
        return ("new_development", "shared named event anchor with a current development marker")
    return ("same_day_duplicate" if distance == 0 else "historical_duplicate", "shared named event anchor and event type")


def event_id_for(group: list[dict]) -> str:
    identities = {canonical_event_identity(row) for row in group if canonical_event_identity(row)}
    if len(identities) == 1:
        identity = next(iter(identities))
        return "event-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    common = None
    for row in group[1:]:
        terms = meaningful_terms(clean_discovery_title(row.get("title", "")))
        common = terms if common is None else common & terms
    if not common:
        common = meaningful_terms(clean_discovery_title(group[0].get("title", "")))
    identity = "|".join(sorted(term for term in common if len(term) >= 4)) or event_key(group[0])
    return "event-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]


def compact_discovery_report(row: dict) -> dict:
    return {
        key: row.get(key)
        for key in ("title", "url", "publishedDate", "discoveredVia", "discoverySourceType", "discoveryQuery", "queryFamily", "sourceDomain", "duplicateStatus", "duplicateOrigin")
        if row.get(key) is not None
    }


def aggregate_event_candidates(records: list[dict]) -> list[dict]:
    """Collapse current-window reports into event candidates before scoring."""
    groups: list[list[dict]] = []
    for row in records:
        if row.get("duplicateStatus") == "historical_duplicate":
            continue
        for group in groups:
            relation = event_report_relation(row, group[0])
            if relation:
                group.append(row)
                break
        else:
            groups.append([row])
    # A report may have been marked historical because it matched an older
    # daily item, while another report for the same event is also present in
    # this replay window. Keep that report only when it matches a current
    # event group; history-only repeats stay out of the candidate pool.
    for row in records:
        if row.get("duplicateStatus") != "historical_duplicate":
            continue
        for group in groups:
            if event_report_relation(row, group[0]):
                group.append(row)
                break
    events = []
    used_event_ids = set()
    for group in groups:
        # Prefer a directly classified A/B URL as representative; otherwise use
        # the most informative title while preserving all discovery reports.
        ranked = sorted(
            group,
            key=lambda row: (
                1 if source_info(row.get("url", "")).get("tier") in {"A", "B"} else 0,
                len(clean_discovery_title(row.get("title", ""))),
            ),
            reverse=True,
        )
        representative = ranked[0]
        title = clean_discovery_title(representative.get("title", ""))
        dates = [row.get("publishedDate") for row in group if row.get("publishedDate")]
        scopes = [row.get("scope", "domestic") for row in group]
        source_domains = sorted({row.get("sourceDomain") for row in group if row.get("sourceDomain")})
        event_id = event_id_for(group)
        if event_id in used_event_ids:
            # Identity terms can legitimately collide for separate reports
            # such as generic "政策解读" pages. Keep the semantic base ID,
            # but make the collision deterministic from this group's URLs.
            signature = "|".join(sorted(canonical_url(row.get("url") or "") for row in group))
            suffix = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:8]
            event_id = f"{event_id}-{suffix}"
            counter = 2
            while event_id in used_event_ids:
                event_id = f"{event_id_for(group)}-{suffix}-{counter}"
                counter += 1
        used_event_ids.add(event_id)
        event = {
            "eventId": event_id,
            "title": title,
            "representativeTitle": title,
            "url": representative.get("url", ""),
            "publishedDate": max(dates) if dates else representative.get("publishedDate", ""),
            "scope": "international" if scopes.count("international") > len(scopes) / 2 else "domestic",
            "newDevelopment": any(row.get("newDevelopment") is True for row in group),
            "discoveryReports": [compact_discovery_report(row) for row in group],
            "reportCount": len(group),
            "sourceDomains": source_domains,
        }
        events.append(event)
        for row in group:
            row["eventId"] = event["eventId"]
    return events


def evidence_upgrade_queries(event: dict) -> list[str]:
    """Build bounded, event-specific searches without using source tier as rank."""
    title = clean_discovery_title(event.get("representativeTitle") or event.get("title", ""))
    terms = [
        term for term in meaningful_terms(title)
        if len(term) >= 3
        and term not in EVIDENCE_CONTEXT_TERMS
        and term not in GENERIC_EVENT_WORDS
        and not EVIDENCE_CONTEXT_PATTERNS.search(term)
        and not re.fullmatch(r"\d+", term)
        and not re.search(r"\d", term)
    ]
    # Prefer named Chinese phrases and keep the anchor small.  Metrics and
    # event verbs make source searches noisy without improving identity
    # matching; parse_rss still applies the requested date window.
    cjk_terms = sorted((term for term in terms if re.search(r"[\u4e00-\u9fff]", term)), key=lambda term: (-len(term), term))
    latin_terms = sorted((term for term in terms if re.fullmatch(r"[a-z][a-z0-9-]{3,}", term)), key=lambda term: (-len(term), term))
    anchor_terms = cjk_terms[:1] if cjk_terms else latin_terms[:3]
    anchor_query = " ".join(anchor_terms)
    suffix = " 官方原文" if event.get("scope") != "international" else " official source"
    queries = [title + suffix]
    if anchor_query and anchor_query not in title:
        queries.append(anchor_query + suffix)
    elif anchor_query:
        queries.append(anchor_query)
    for domain in event.get("sourceDomains", []):
        if re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", str(domain or "").lower()) and domain not in {"news.google.com", "bing.com"}:
            queries.append(f"site:{domain} {anchor_query or title}")
            # A named event plus one concrete fact is often indexed more
            # reliably than the title alone.  Keep this generic: derive the
            # qualifier from the event title instead of baking in a headline.
            qualifiers = re.findall(r"\d+(?:\.\d+)?(?:万|亿|人次|件|种|个月|亿元|万元)", title)
            if anchor_query and qualifiers:
                queries.append(f"site:{domain} {anchor_query} {qualifiers[0]}")
    return list(dict.fromkeys(query for query in queries if query.strip()))


class _EvidenceMetaParser(HTMLParser):
    """Collect publisher URLs exposed by ordinary article metadata."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        values = {str(key).lower(): value for key, value in attrs}
        if tag.lower() == "link" and str(values.get("rel", "")).lower() == "canonical":
            value = values.get("href")
        elif tag.lower() == "meta" and str(values.get("property", "")).lower() in {"og:url", "og:see_also"}:
            value = values.get("content")
        elif tag.lower() == "meta" and str(values.get("name", "")).lower() in {"original-source", "source_url", "source-url"}:
            value = values.get("content")
        else:
            value = None
        if value:
            self.urls.append(value.strip())


def unwrap_redirect_url(url: str) -> tuple[str, bool]:
    """Extract an embedded publisher URL from common news redirect links."""
    original = url or ""
    parts = urlsplit(original)
    host = (parts.hostname or "").lower()
    if host.endswith("bing.com") and parts.path.lower().endswith("/apiclick.aspx"):
        embedded = parse_qs(parts.query).get("url", [""])[0]
        if embedded:
            return unquote(embedded), True
    # Some providers use a generic redirect endpoint with a url/u/target
    # parameter. Only accept an absolute HTTP(S) target; arbitrary query text
    # must never become an evidence URL.
    if host.endswith("google.com") or host.endswith("googleusercontent.com"):
        for key in ("url", "u", "target", "dest", "destination"):
            embedded = parse_qs(parts.query).get(key, [""])[0]
            if urlsplit(embedded).scheme in {"http", "https"}:
                return unquote(embedded), True
    return original, False


def metadata_urls(base_url: str, body: str) -> list[str]:
    parser = _EvidenceMetaParser()
    try:
        parser.feed(body or "")
    except Exception:
        return []
    candidates = []
    for value in parser.urls:
        candidate = urljoin(base_url, value)
        if urlsplit(candidate).scheme in {"http", "https"} and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def resolve_evidence_url(url: str) -> tuple[str, str, str | None]:
    """Follow redirects/canonical metadata and retrieve a bounded source sample."""
    url, _ = unwrap_redirect_url(url)
    request = Request(url, headers={"User-Agent": SEARCH_USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"})
    try:
        with SEARCH_OPENER.open(request, timeout=8) as response:
            resolved = response.geturl() or url
            body = response.read(256_000).decode("utf-8", errors="replace")
        # A publisher page may explicitly expose the canonical/original URL.
        # Follow only a non-aggregator HTTP(S) metadata target, and keep the
        # first page as a fallback if the metadata target is unavailable.
        for candidate in metadata_urls(resolved, body):
            candidate_host = (urlsplit(candidate).hostname or "").lower()
            if candidate_host.endswith(("news.google.com", "bing.com")) or canonical_url(candidate) == canonical_url(resolved):
                continue
            actual = source_info(candidate)
            if actual.get("tier") not in {"A", "B"}:
                continue
            try:
                follow_request = Request(candidate, headers={"User-Agent": SEARCH_USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"})
                with SEARCH_OPENER.open(follow_request, timeout=8) as follow_response:
                    followed = follow_response.geturl() or candidate
                    followed_body = follow_response.read(256_000).decode("utf-8", errors="replace")
                return followed, followed_body, None
            except Exception:
                continue
        return resolved, body, None
    except Exception as exc:
        return url, "", f"{type(exc).__name__}: {exc}"


def evidence_matches_event(event: dict, result: dict, body: str) -> bool:
    event_terms = meaningful_terms(clean_discovery_title(event.get("representativeTitle") or event.get("title", "")))
    result_text = clean_discovery_title(result.get("title", "")) + " " + re.sub(r"<[^>]+>", " ", body or "")[:12000]
    result_terms = meaningful_terms(result_text)
    shared = event_terms & result_terms
    named = {term for term in shared if len(term) >= 4 and term not in GENERIC_EVENT_WORDS}
    return bool(named) or (len(shared) >= 2 and bool(event_terms))


def resolve_evidence_attempt(event: dict, result: dict, method: str) -> tuple[dict, dict | None]:
    """Resolve one report and return an auditable attempt plus publishable source."""
    input_url = result.get("url", "")
    unwrapped_url, unwrapped = unwrap_redirect_url(input_url)
    attempts = []
    if unwrapped:
        unwrapped_actual = source_info(unwrapped_url)
        attempts.append({
            "method": "redirect_unwrap",
            "inputUrl": input_url,
            "resolvedUrl": unwrapped_url,
            "domain": (urlsplit(unwrapped_url).hostname or "").lower(),
            "fetchStatus": "resolved",
            "articleMatched": False,
            "evidenceTier": unwrapped_actual.get("tier", "C"),
        })
    resolved_url, body, resolve_error = resolve_evidence_url(unwrapped_url)
    actual = source_info(resolved_url)
    matched = False
    if not resolve_error and not actual.get("blocked") and actual.get("tier") in {"A", "B"}:
        matched = evidence_matches_event(event, result, body)
    attempts.append({
        "method": method,
        "inputUrl": input_url,
        "resolvedUrl": resolved_url,
        "domain": (urlsplit(resolved_url).hostname or "").lower(),
        "fetchStatus": "ok" if not resolve_error else "failed",
        "articleMatched": matched,
        "evidenceTier": actual.get("tier", "C"),
    })
    checked = {
        "discoveryUrl": input_url,
        "url": resolved_url,
        "title": result.get("title", ""),
        "tier": actual.get("tier", "C"),
        "retrieved": not bool(resolve_error),
        "matched": matched,
        "error": resolve_error,
        "method": method,
    }
    publishable = None
    if matched:
        publishable = {
            "name": result.get("title", ""),
            "url": resolved_url,
            "tier": actual.get("tier", "C"),
            "role": "evidence-upgrade",
        }
    return {"attempts": attempts, "checked": checked}, publishable


def run_evidence_upgrade(required_date: date, events: list[dict]) -> dict:
    """Actually search, retrieve and assess evidence for queued event candidates."""
    queued = [
        event for event in events
        if event.get("candidateDisposition") == "needs_verification"
        and (event.get("editorialPriorityLabel") == "high" or event.get("editorialPriorityScore", 0) >= 55)
    ]
    attempted = qualified = failed = ambiguous = 0
    upgrade_rows = []
    query_jobs = []
    for event in queued:
        family = {"id": "evidence-upgrade", "scope": event.get("scope", "domestic")}
        for base_query in evidence_upgrade_queries(event):
            for backend in QUERY_BACKENDS:
                # Exact source-domain queries get a fallback without date
                # operators. The RSS item dates are still filtered by
                # parse_rss, while this helps engines that ignore or mishandle
                # after:/before: for older indexed source pages.
                query_jobs.append((event["eventId"], family, backend, base_query, not base_query.startswith("site:")))
    query_results = {event_id: [] for event_id in {event["eventId"] for event in queued}}
    with ThreadPoolExecutor(max_workers=min(8, len(query_jobs) or 1)) as pool:
        futures = {
            pool.submit(_execute_one_query, family, backend, base_query, required_date - timedelta(days=6), required_date, date_filter=date_filter): event_id
            for event_id, family, backend, base_query, date_filter in query_jobs
        }
        for future in as_completed(futures):
            event_id = futures[future]
            try:
                found, audit = future.result()
            except Exception as exc:
                found, audit = [], {
                    "queryFamily": "evidence-upgrade",
                    "actualQuery": "",
                    "executedAt": now_cn(),
                    "success": False,
                    "failure": f"{type(exc).__name__}: {exc}",
                    "returnedResultCount": 0,
                    "acceptedRawCount": 0,
                }
            query_results[event_id].append((found, audit))
    for event in queued:
        attempted += 1
        query_audits = []
        checked_sources = []
        resolution_attempts = []
        publishable = []
        had_query_failure = False
        had_resolution_failure = False
        seen_result_urls = set()
        # Existing reports are the cheapest and most reliable path to a
        # publisher page.  A report may still contain a Google/Bing wrapper;
        # the resolver audit records that separately instead of discarding it.
        existing_reports = event.get("discoveryReports") or []
        for report in existing_reports:
            report_url = canonical_url(report.get("url", ""))
            if not report_url or report_url in seen_result_urls:
                continue
            seen_result_urls.add(report_url)
            method = "existing_report"
            outcome, source = resolve_evidence_attempt(event, report, method)
            resolution_attempts.extend(outcome["attempts"])
            checked_sources.append(outcome["checked"])
            had_resolution_failure = had_resolution_failure or bool(outcome["checked"].get("error"))
            if source:
                publishable.append(source)
        for found, audit in sorted(query_results.get(event["eventId"], []), key=lambda row: (row[1].get("actualQuery", ""), row[1].get("executedAt", ""))):
            query_audits.append(audit)
            had_query_failure = had_query_failure or not audit.get("success")
            for result in found:
                result_url = canonical_url(result.get("url", ""))
                if result_url in seen_result_urls:
                    continue
                seen_result_urls.add(result_url)
                query_text = audit.get("actualQuery", "")
                if query_text.startswith("site:"):
                    method = "domain_search"
                elif "官方原文" in query_text or "official source" in query_text:
                    method = "official_search"
                else:
                    method = "broad_search"
                # RSS searches often return a large page of unrelated stories
                # from the same publisher.  Screen by the event title before
                # opening article pages; this is a recall-preserving guard for
                # retrieval cost, not an evidence qualification decision.
                if not evidence_matches_event(event, result, ""):
                    result_domain = (urlsplit(result.get("url", "")).hostname or "").lower()
                    resolution_attempts.append({
                        "method": method,
                        "inputUrl": result.get("url", ""),
                        "resolvedUrl": result.get("url", ""),
                        "domain": result_domain,
                        "fetchStatus": "screened_out",
                        "articleMatched": False,
                        "evidenceTier": source_info(result.get("url", "")).get("tier", "C"),
                    })
                    checked_sources.append({
                        "discoveryUrl": result.get("url", ""),
                        "url": result.get("url", ""),
                        "title": result.get("title", ""),
                        "tier": source_info(result.get("url", "")).get("tier", "C"),
                        "retrieved": False,
                        "matched": False,
                        "error": "title_not_matched_to_event",
                        "method": method,
                    })
                    continue
                outcome, source = resolve_evidence_attempt(event, result, method)
                resolution_attempts.extend(outcome["attempts"])
                checked_sources.append(outcome["checked"])
                had_resolution_failure = had_resolution_failure or bool(outcome["checked"].get("error"))
                if source:
                    publishable.append(source)
        unique_sources = {}
        for source in publishable:
            unique_sources[canonical_url(source["url"])] = source
        publishable = list(unique_sources.values())
        event["evidenceUpgradeAttempted"] = True
        event["evidenceUpgradeQueries"] = query_audits
        event["evidenceUpgradeSourcesChecked"] = checked_sources
        event["evidenceResolutionAttempts"] = resolution_attempts
        if publishable:
            best = sorted(publishable, key=lambda row: (0 if row["tier"] == "A" else 1, row["url"]))[0]
            event["evidenceSources"] = publishable
            event["evidenceTierAfterUpgrade"] = best["tier"]
            event["evidenceUpgradeResult"] = "qualified"
            event["evidenceFailureReason"] = None
            event["candidateDisposition"] = "evidence_qualified"
            event["evidenceUpgradeStatus"] = "completed"
            qualified += 1
        else:
            event["evidenceTierAfterUpgrade"] = "C"
            event["evidenceUpgradeResult"] = "ambiguous" if had_query_failure or had_resolution_failure else "failed"
            event["evidenceFailureReason"] = "search_or_retrieval_incomplete" if (had_query_failure or had_resolution_failure) else "no_publishable_matching_A_or_B_source"
            event["evidenceUpgradeStatus"] = event["evidenceUpgradeResult"]
            if event["evidenceUpgradeResult"] == "ambiguous":
                ambiguous += 1
            else:
                failed += 1
        upgrade_rows.append(event)
    return {"attempted": attempted, "qualified": qualified, "failed": failed, "ambiguous": ambiguous, "events": upgrade_rows}


def event_key(record: dict) -> str:
    explicit = record.get("canonicalEventId")
    if explicit:
        return str(explicit)
    identity = canonical_event_identity(record)
    if identity:
        return identity
    title = record.get("title", "") or ""
    # Policy documents are often republished by several official or media
    # pages with different prefixes.  Use the named instrument as the event
    # identity, while leaving unrelated policy titles on the normal path.
    policy_match = re.search(r"[\u4e00-\u9fff]{2,16}(?:管理办法|实施办法|保护条例|条例|办法|规定|规程)", title)
    if policy_match:
        return "policy|" + compact(policy_match.group(0))
    bits = [title]
    terms = sorted(meaningful_terms(" ".join(bits)))
    return "|".join(terms[:12])


def duplicate_relation(current: dict, previous: dict) -> tuple[str, str] | None:
    current_url = canonical_url(current.get("url") or current.get("evidenceUrl") or "")
    previous_url = canonical_url(previous.get("url") or previous.get("evidenceUrl") or "")
    if current_url and previous_url and current_url == previous_url:
        return ("same_day_duplicate" if current.get("publishedDate") == previous.get("publishedDate") else "historical_duplicate", "same canonical URL")
    current_key = canonical_event_identity(current) or event_key(current)
    previous_key = canonical_event_identity(previous) or event_key(previous)
    if current_key and current_key == previous_key:
        if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
            return ("new_development", "same event identity but current record contains a substantive development marker")
        return ("same_day_duplicate" if current.get("publishedDate") == previous.get("publishedDate") else "historical_duplicate", "same event identity")
    left = meaningful_terms(current.get("title", ""))
    right = meaningful_terms(previous.get("title", ""))
    shared = left & right
    # Similar subject matter is not enough.  Require a substantial overlap
    # plus a shared named anchor, so two different archaeological sites are
    # not silently merged.
    named_shared = {term for term in shared if len(term) >= 4 and term not in GENERIC_EVENT_WORDS}
    close_in_time = False
    try:
        close_in_time = abs(date.fromisoformat(current.get("publishedDate", "")) - date.fromisoformat(previous.get("publishedDate", ""))) <= timedelta(days=1)
    except ValueError:
        pass
    if len(named_shared) >= 2 and (
        len(shared) / max(1, min(len(left), len(right))) >= 0.4 or close_in_time
    ):
        if any(word in (current.get("title", "") + current.get("notes", "")) for word in DEVELOPMENT_WORDS):
            return ("new_development", "high-overlap event identity with a substantive development marker")
        return ("historical_duplicate", "high-overlap event identity")
    return None


def build_final_editorial_pool(evaluation: dict, historical_duplicate_count: int = 0) -> dict:
    """Expose one event-level, publishable input for the final editor.

    This is intentionally not the editorial selector.  Codex still decides
    selected/rejected/deferred after reviewing these events.  The pool only
    prevents the old candidate ledger and the evidence-upgrade audit from
    becoming two competing input sets.
    """
    qualified = [
        row for row in evaluation.get("pool", [])
        if row.get("candidateDisposition") == "evidence_qualified"
    ]
    canonical_events = {}
    for row in qualified:
        event_id = row.get("eventId")
        if event_id and event_id not in canonical_events:
            canonical_events[event_id] = row
    event_ids = set(canonical_events)
    fields = (
        "eventId", "title", "representativeTitle", "url", "publishedDate", "scope",
        "candidateDisposition",
        "reportCount", "sourceDomains", "freshnessTier", "newDevelopment",
        "editorialPriorityScore", "editorialPriorityLabel", "editorialReasons",
        "evidenceTierAtDiscovery", "evidenceTierAfterUpgrade", "evidenceUpgradeStatus",
        "evidenceUpgradeAttempted", "evidenceUpgradeResult", "evidenceSources",
        "evidenceResolutionAttempts", "discoveryReports",
    )
    return {
        "status": "pending_editorial_review",
        "rawQualifiedEvents": len(qualified),
        "canonicalUniqueEvents": len(event_ids),
        # Historical duplicates are removed before candidate evaluation. Keep
        # the count here as an explicit upstream exclusion, not as pool rows.
        "historicalDuplicates": historical_duplicate_count,
        "historicalDuplicateDefinition": "unique published-event targets excluded before evidence qualification",
        "editoriallyReviewed": 0,
        "events": [{key: row.get(key) for key in fields} for row in canonical_events.values()],
    }


def freshness_tier(required_date: date, published_value: str) -> str:
    try:
        age = (required_date - date.fromisoformat(published_value)).days
    except (TypeError, ValueError):
        return "unknown"
    if 0 <= age <= 2:
        return "primary_0_48h"
    if 3 <= age <= 6:
        return "backfill_3_7d"
    return "outside_window"


def is_relevant_record(record: dict) -> bool:
    return any(term.lower() in (record.get("title", "") or "").lower() for term in RELEVANCE_TERMS)


def is_high_value_record(record: dict) -> bool:
    title = (record.get("title", "") or "").lower()
    return any(term.lower() in title for term in HIGH_VALUE_TERMS)


def editorial_priority(record: dict, required_date: date | None = None) -> dict:
    """Score news value before evidence qualification, without using source tier."""
    title = record.get("title", "") or ""
    text = title.lower()
    score = 20
    reasons = []

    def hit(terms):
        return any(term.lower() in text for term in terms)

    policy = hit(POLICY_PRIORITY_TERMS)
    national_policy = policy and hit(NATIONAL_POLICY_TERMS)
    major_discovery = hit(MAJOR_DISCOVERY_TERMS)
    archaeology_discovery = hit(ARCHAEOLOGY_DISCOVERY_TERMS) and hit(("考古", "遗址", "墓", "文物"))
    security = hit(SECURITY_PRIORITY_TERMS)
    repatriation = hit(REPATRIATION_TERMS)
    heritage = hit(HERITAGE_RECOGNITION_TERMS)
    museum_project = hit(MUSEUM_PROJECT_TERMS)
    digital = hit(DIGITAL_PRIORITY_TERMS)
    cooperation = hit(COOPERATION_TERMS)
    routine = hit(ROUTINE_PRIORITY_TERMS)

    if national_policy:
        score += 58
        reasons.append("national_or_industry_policy")
    elif policy:
        score += 42
        reasons.append("policy_or_governance_update")
    if major_discovery:
        score += 48
        reasons.append("major_archaeological_or_heritage_discovery_signal")
    elif archaeology_discovery:
        score += 34
        reasons.append("substantive_archaeological_discovery_or_new_knowledge")
    if security:
        score += 43
        reasons.append("museum_or_cultural_property_security_event")
    if repatriation:
        score += 36
        reasons.append("repatriation_or_recovery_update")
    if heritage:
        score += 36
        reasons.append("heritage_recognition_or_world_heritage_update")
    if museum_project:
        score += 28
        reasons.append("significant_museum_or_exhibition_project")
        if hit(MUSEUM_SCALE_TERMS):
            score += 20
            reasons.append("substantive_audience_or_operation_data")
    if digital:
        score += 24
        reasons.append("substantive_digital_or_technology_project")
    if cooperation:
        score += 20
        reasons.append("meaningful_institutional_or_international_cooperation")
    if record.get("newDevelopment") is True:
        score += 12
        reasons.append("new_development")
    if required_date:
        tier = freshness_tier(required_date, record.get("publishedDate"))
        if tier == "primary_0_48h":
            score += 8
            reasons.append("primary_freshness")
        elif tier == "backfill_3_7d":
            score += 2
            reasons.append("backfill_freshness")
    if routine:
        # Routine labels alone do not erase a substantive policy, discovery,
        # security or heritage signal, but they prevent ordinary activities
        # from outranking core industry events merely because they are easy to verify.
        penalty = 30 if not (national_policy or major_discovery or archaeology_discovery or security or repatriation or heritage) else 12
        score -= penalty
        reasons.append("routine_or_peripheral_activity_penalty")
    if not reasons:
        reasons.append("general_relevance_only")
    score = max(0, min(100, score))
    label = "high" if score >= 70 else "medium" if score >= 45 else "low"
    return {"score": score, "label": label, "reasons": reasons}


def evaluate_candidate_pool(required_date: date, records: list[dict], raw_priority_counts: dict | None = None, raw_record_count: int | None = None) -> dict:
    """Rank news value first, then apply transparent evidence/editorial gates."""
    evaluated = []
    ranked = sorted(
        records,
        key=lambda row: (
            editorial_priority(row, required_date)["score"],
            row.get("publishedDate", ""),
            row.get("title", ""),
        ),
        reverse=True,
    )
    for rank, original in enumerate(ranked, 1):
        record = dict(original)
        priority = editorial_priority(record, required_date)
        tier = freshness_tier(required_date, record.get("publishedDate"))
        reasons = []
        disposition = "candidate"
        if tier == "outside_window":
            reasons.append("outside_window")
            disposition = "rejected"
        if record.get("duplicateStatus") in {"same_day_duplicate", "historical_duplicate"}:
            reasons.append(record["duplicateStatus"])
            disposition = "rejected"
        if not is_relevant_record(record):
            reasons.append("not_wenbo_relevant")
            disposition = "rejected"
        high_value = is_high_value_record(record)
        routine = any(term.lower() in (record.get("title", "") or "").lower() for term in ROUTINE_TERMS)
        if disposition != "rejected" and routine and not high_value:
            reasons.append("routine_or_promotional")
            disposition = "rejected"
        if disposition != "rejected" and tier == "backfill_3_7d" and not high_value:
            reasons.append("backfill_low_priority")
            disposition = "deferred"
        direct_url = record.get("url", "")
        evidence = source_info(direct_url) if direct_url else {"tier": "C", "blocked": True}
        if disposition == "candidate" and (evidence.get("blocked") or evidence.get("tier") not in {"A", "B"}):
            reasons.append("discovery_only_needs_evidence_upgrade")
            disposition = "needs_verification"
        if disposition == "candidate":
            disposition = "evidence_qualified"
        record["freshnessTier"] = tier
        record["highValueSignal"] = high_value
        record["filterReasons"] = reasons
        record["candidateDisposition"] = disposition
        record["evidenceTierAtDiscovery"] = evidence.get("tier", "C")
        record["editorialPriorityScore"] = priority["score"]
        record["editorialPriorityLabel"] = priority["label"]
        record["editorialReasons"] = priority["reasons"]
        record["editorialPriorityRank"] = rank
        record["evidenceUpgradeStatus"] = "queued" if disposition == "needs_verification" else "not_needed" if disposition == "evidence_qualified" else "not_eligible"
        evaluated.append(record)
    pool = [r for r in evaluated if r["candidateDisposition"] in {"evidence_qualified", "needs_verification"}]
    high_priority_queue = [
        r for r in pool
        if r["editorialPriorityLabel"] == "high" and r["candidateDisposition"] == "needs_verification"
    ]
    high_priority_queue.sort(key=lambda row: row["editorialPriorityScore"], reverse=True)
    medium_priority_queue = [
        r for r in pool
        if r["candidateDisposition"] == "needs_verification"
        and r["editorialPriorityLabel"] == "medium"
        and r["editorialPriorityScore"] >= 55
    ]
    medium_priority_queue.sort(key=lambda row: row["editorialPriorityScore"], reverse=True)
    provisional = [
        r for r in pool
        if r["candidateDisposition"] == "evidence_qualified"
        and r["freshnessTier"] == "primary_0_48h"
        and r["editorialPriorityLabel"] == "high"
    ]
    def counts(rows):
        from collections import Counter
        return dict(Counter(r.get("candidateDisposition") for r in rows))
    return {
        "records": evaluated,
        "pool": pool,
        "highPriorityEvidenceQueue": high_priority_queue,
        "mediumPriorityEvidenceQueue": medium_priority_queue,
        "provisionalWouldBeSelected": provisional,
        "summary": {
            "rawRecords": raw_record_count if raw_record_count is not None else len(records),
            "eventCandidateCount": len(records),
            "deduplicatedReports": sum(r.get("reportCount", 1) for r in records),
            "candidateEvaluationPool": len(pool),
            "evidenceQualified": sum(r["candidateDisposition"] == "evidence_qualified" for r in pool),
            "needsVerification": sum(r["candidateDisposition"] == "needs_verification" for r in pool),
            "highPriorityCandidates": sum(r["editorialPriorityLabel"] == "high" for r in pool),
            "highPriorityEvidenceQueue": len(high_priority_queue),
            "highPriorityNeedsVerification": len(high_priority_queue),
            "highPriorityEvidenceQueueEvents": len(high_priority_queue),
            "mediumPriorityEvidenceQueueEvents": len(medium_priority_queue),
            "evidenceUpgradeAttempted": 0,
            "evidenceUpgradeQualified": 0,
            "evidenceUpgradeFailed": 0,
            "evidenceUpgradeAmbiguous": 0,
            "rejected": sum(r["candidateDisposition"] == "rejected" for r in evaluated),
            "deferred": sum(r["candidateDisposition"] == "deferred" for r in evaluated),
            "provisionalWouldBeSelected": len(provisional),
            "editorialPriorityCounts": {
                "high": sum(r["editorialPriorityLabel"] == "high" for r in evaluated),
                "medium": sum(r["editorialPriorityLabel"] == "medium" for r in evaluated),
                "low": sum(r["editorialPriorityLabel"] == "low" for r in evaluated),
            },
            "eventCandidatePriorityCounts": {
                "high": sum(r["editorialPriorityLabel"] == "high" for r in evaluated),
                "medium": sum(r["editorialPriorityLabel"] == "medium" for r in evaluated),
                "low": sum(r["editorialPriorityLabel"] == "low" for r in evaluated),
            },
            "rawRecordPriorityCounts": raw_priority_counts or {},
            "dispositionCounts": counts(evaluated),
        },
    }


def scan_page(spec: dict, start: date, end: date) -> tuple[dict, list[dict]]:
    status = {"sourceId": spec["sourceId"], "name": spec["name"], "scope": spec["scope"], "url": spec["url"], "status": "fetch_failed", "linksSeen": 0, "datedLinks": 0, "outsideWindow": 0, "undatedLinks": 0, "rawResults": 0, "windowResults": 0, "note": ""}
    try:
        page = fetch(spec["url"])
    except Exception as exc:
        status["note"] = str(exc)
        return status, []
    status["status"] = "checked"
    records = []
    for anchor_title, url in links(page, spec["url"]):
        status["linksSeen"] += 1
        published = parse_date(url) or parse_date(anchor_title)
        if not published:
            status["undatedLinks"] += 1
            continue
        status["datedLinks"] += 1
        status["rawResults"] += 1
        if not (start <= published <= end):
            status["outsideWindow"] += 1
            continue
        record = {
            "title": anchor_title.strip(),
            "publishedDate": published.isoformat(),
            "url": url,
            "discoveredVia": spec["sourceId"],
            "discoverySourceType": "source_scan",
            "scope": spec["scope"],
            "sourceDomain": spec["domain"],
        }
        records.append(record)
    status["windowResults"] = len(records)
    return status, records


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_history(required_date: date) -> list[dict]:
    rows = []
    daily_dir = ROOT / "content" / "日报"
    for path in sorted(daily_dir.glob("????-??-??.md")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        # The report being replayed is not historical evidence.  Including it
        # here would label a just-discovered item as a historical duplicate of
        # the very report the replay is meant to evaluate.
        if required_date - timedelta(days=30) <= day < required_date:
            try:
                from build import parse_md
                parsed = parse_md(path)
            except Exception:
                continue
            for item in parsed.get("domestic", []) + parsed.get("international", []):
                row = {
                    "title": item.get("title", ""),
                    "body": item.get("body", ""),
                    "notes": item.get("commentary", ""),
                    "publishedDate": parsed.get("date", ""),
                    "url": (item.get("sources") or [{}])[0].get("url", ""),
                    "historicalSource": "published_daily_markdown",
                }
                identity = canonical_event_identity(row)
                if identity:
                    row["canonicalIdentity"] = identity
                    row["historicalCanonicalEventId"] = "published-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
                rows.append(row)
    return rows


def build_audit(required_date: date, raw_records: list[dict], scan_statuses: list[dict], query_results: list[dict], query_audits: list[dict] | None = None, perform_evidence_upgrade: bool = False) -> dict:
    start = required_date - timedelta(days=6)
    history = load_history(required_date)
    combined = []
    seen_urls = set()
    for record in raw_records + query_results:
        url = canonical_url(record.get("url") or record.get("discoveryUrl") or "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        record = dict(record)
        record.setdefault("discoveredAt", now_cn())
        combined.append(record)
    same_day = historical = developments = 0
    annotated = []
    for record in combined:
        relation = None
        for previous in annotated + history:
            relation = duplicate_relation(record, previous)
            if relation:
                break
        if relation:
            status, reason = relation
            record["duplicateStatus"] = status
            record["duplicateReason"] = reason
            record["duplicateOf"] = (
                previous.get("historicalCanonicalEventId")
                or previous.get("canonicalEventId")
                or previous.get("title")
            )
            record["duplicateOfTitle"] = previous.get("title", "")
            record["newDevelopment"] = status == "new_development"
            if status == "same_day_duplicate":
                same_day += 1
            elif status == "historical_duplicate":
                historical += 1
            elif status == "new_development":
                developments += 1
        else:
            record.setdefault("duplicateStatus", "unique_event")
            record.setdefault("newDevelopment", False)
        annotated.append(record)
    raw_priority_counts = {"high": 0, "medium": 0, "low": 0}
    for row in annotated:
        raw_priority_counts[editorial_priority(row, required_date)["label"]] += 1
    report_records = annotated
    event_candidates = aggregate_event_candidates(report_records)
    evaluation = evaluate_candidate_pool(required_date, event_candidates, raw_priority_counts=raw_priority_counts, raw_record_count=len(report_records))
    if perform_evidence_upgrade:
        upgrade = run_evidence_upgrade(required_date, evaluation["records"])
        evaluation["summary"]["evidenceUpgradeAttempted"] = upgrade["attempted"]
        evaluation["summary"]["evidenceUpgradeQualified"] = upgrade["qualified"]
        evaluation["summary"]["evidenceUpgradeFailed"] = upgrade["failed"]
        evaluation["summary"]["evidenceUpgradeAmbiguous"] = upgrade["ambiguous"]
        evaluation["pool"] = [row for row in evaluation["records"] if row["candidateDisposition"] in {"evidence_qualified", "needs_verification"}]
        evaluation["highPriorityEvidenceQueue"] = [row for row in evaluation["pool"] if row["candidateDisposition"] == "needs_verification" and row["editorialPriorityLabel"] == "high"]
        evaluation["mediumPriorityEvidenceQueue"] = [row for row in evaluation["pool"] if row["candidateDisposition"] == "needs_verification" and row["editorialPriorityLabel"] == "medium" and row["editorialPriorityScore"] >= 55]
        evaluation["highPriorityEvidenceQueue"].sort(key=lambda row: row["editorialPriorityScore"], reverse=True)
        evaluation["mediumPriorityEvidenceQueue"].sort(key=lambda row: row["editorialPriorityScore"], reverse=True)
        evaluation["summary"]["candidateEvaluationPool"] = len(evaluation["pool"])
        evaluation["summary"]["evidenceQualified"] = sum(row["candidateDisposition"] == "evidence_qualified" for row in evaluation["pool"])
        evaluation["summary"]["needsVerification"] = sum(row["candidateDisposition"] == "needs_verification" for row in evaluation["pool"])
        evaluation["summary"]["highPriorityCandidates"] = sum(row["editorialPriorityLabel"] == "high" for row in evaluation["pool"])
        evaluation["summary"]["highPriorityEvidenceQueue"] = len(evaluation["highPriorityEvidenceQueue"])
        evaluation["summary"]["highPriorityNeedsVerification"] = len(evaluation["highPriorityEvidenceQueue"])
        evaluation["summary"]["highPriorityEvidenceQueueEvents"] = len(evaluation["highPriorityEvidenceQueue"])
        evaluation["summary"]["mediumPriorityEvidenceQueueEvents"] = len(evaluation["mediumPriorityEvidenceQueue"])
        evaluation["summary"]["provisionalWouldBeSelected"] = sum(
            row["candidateDisposition"] == "evidence_qualified"
            and row["freshnessTier"] == "primary_0_48h"
            and row["editorialPriorityLabel"] == "high"
            for row in evaluation["pool"]
        )
        evaluation["provisionalWouldBeSelected"] = [
            row for row in evaluation["pool"]
            if row["candidateDisposition"] == "evidence_qualified"
            and row["freshnessTier"] == "primary_0_48h"
            and row["editorialPriorityLabel"] == "high"
        ]
        evaluation["summary"]["dispositionCounts"] = {
            disposition: sum(row.get("candidateDisposition") == disposition for row in evaluation["records"])
            for disposition in {row.get("candidateDisposition") for row in evaluation["records"]}
        }
    evaluated_events = evaluation["records"]
    event_by_id = {row.get("eventId"): row for row in evaluated_events}
    for report in report_records:
        event = event_by_id.get(report.get("eventId"))
        if event:
            report["eventCandidateDisposition"] = event.get("candidateDisposition")
            report["eventEditorialPriorityScore"] = event.get("editorialPriorityScore")
            report["eventEditorialPriorityLabel"] = event.get("editorialPriorityLabel")
    domestic = [row for row in report_records if row.get("scope", "domestic") != "international"]
    international = [row for row in report_records if row.get("scope") == "international"]
    def stats(rows):
        historical = [r for r in rows if r.get("duplicateStatus") == "historical_duplicate"]
        return {
            "rawResults": len(rows),
            "sameDayDuplicateRecords": sum(r.get("duplicateStatus") == "same_day_duplicate" for r in rows),
            "historicalDuplicateRecords": len(historical),
            "historicalDuplicateCanonicalTargets": len({r.get("duplicateOf") for r in historical if r.get("duplicateOf")}),
            "newDevelopmentRecords": sum(r.get("duplicateStatus") == "new_development" for r in rows),
            "deduplicatedResults": sum(r.get("duplicateStatus") in {"unique_event", "new_development"} for r in rows),
        }
    historical_rows = [r for r in report_records if r.get("duplicateStatus") == "historical_duplicate"]
    final_editorial_pool = build_final_editorial_pool(
        evaluation,
        historical_duplicate_count=len({r.get("duplicateOf") for r in historical_rows if r.get("duplicateOf")}),
    )
    return {
        "schema": "daily-discovery-v1",
        "date": required_date.isoformat(),
        "windowStart": start.isoformat(),
        "windowEnd": required_date.isoformat(),
        "cutoffTimezone": "Asia/Shanghai",
        "sourceScans": scan_statuses,
        "queryFamilies": [dict(f, queries=list(f["queries"])) for f in QUERY_FAMILIES],
        "queryAuditStatus": "checked" if query_audits else "not_replayed",
        "queryResults": query_results,
        "queryAudits": query_audits or [],
        "records": report_records,
        "candidateEvaluation": {
            "summary": evaluation["summary"],
            "finalEditorialPool": final_editorial_pool,
            "eventCandidates": [
                {
                    "eventId": row.get("eventId"),
                    "representativeTitle": row.get("representativeTitle"),
                    "publishedDate": row.get("publishedDate"),
                    "scope": row.get("scope"),
                    "reportCount": row.get("reportCount"),
                    "sourceDomains": row.get("sourceDomains"),
                    "discoveryReports": row.get("discoveryReports"),
                }
                for row in event_candidates
            ],
            "pool": [
                {k: row.get(k) for k in ("eventId", "title", "representativeTitle", "url", "publishedDate", "scope", "reportCount", "sourceDomains", "freshnessTier", "candidateDisposition", "evidenceTierAtDiscovery", "evidenceTierAfterUpgrade", "filterReasons", "editorialPriorityScore", "editorialPriorityLabel", "editorialReasons", "editorialPriorityRank", "evidenceUpgradeStatus", "evidenceUpgradeAttempted", "evidenceUpgradeResult", "evidenceFailureReason", "evidenceSources", "evidenceUpgradeQueries", "evidenceUpgradeSourcesChecked", "evidenceResolutionAttempts")}
                for row in evaluation["pool"]
            ],
            "highPriorityEvidenceQueue": [
                {k: row.get(k) for k in ("eventId", "title", "representativeTitle", "url", "publishedDate", "scope", "reportCount", "sourceDomains", "editorialPriorityScore", "editorialPriorityLabel", "editorialReasons", "evidenceTierAtDiscovery", "evidenceTierAfterUpgrade", "evidenceUpgradeAttempted", "evidenceUpgradeResult", "evidenceFailureReason", "evidenceSources", "evidenceUpgradeQueries", "evidenceUpgradeSourcesChecked", "evidenceResolutionAttempts")}
                for row in evaluation["highPriorityEvidenceQueue"]
            ],
            "mediumPriorityEvidenceQueue": [
                {k: row.get(k) for k in ("eventId", "title", "representativeTitle", "url", "publishedDate", "scope", "reportCount", "sourceDomains", "editorialPriorityScore", "editorialPriorityLabel", "editorialReasons", "evidenceTierAtDiscovery", "evidenceTierAfterUpgrade", "evidenceUpgradeAttempted", "evidenceUpgradeResult", "evidenceFailureReason", "evidenceSources", "evidenceUpgradeQueries", "evidenceUpgradeSourcesChecked", "evidenceResolutionAttempts")}
                for row in evaluation["mediumPriorityEvidenceQueue"]
            ],
            "provisionalWouldBeSelected": [
                {k: row.get(k) for k in ("title", "url", "publishedDate", "scope", "freshnessTier", "candidateDisposition")}
                for row in evaluation["provisionalWouldBeSelected"]
            ],
        },
        "summary": {
            "sourceScansAttempted": len(scan_statuses),
            "sourceScansSucceeded": sum(s.get("status") == "checked" for s in scan_statuses),
            "queriesExecuted": sum(bool(a.get("success")) for a in (query_audits or [])),
            "queriesAttempted": len(query_audits or []),
            "queriesSucceeded": sum(bool(a.get("success")) for a in (query_audits or [])),
            "queriesFailed": sum(not bool(a.get("success")) for a in (query_audits or [])),
            "rawResults": len(report_records),
            "sameDayDuplicateRecords": same_day,
            "historicalDuplicateRecords": historical,
            "historicalDuplicateCanonicalTargets": len({r.get("duplicateOf") for r in historical_rows if r.get("duplicateOf")}),
            "newDevelopmentRecords": developments,
            "deduplicatedResults": sum(r.get("duplicateStatus") in {"unique_event", "new_development"} for r in report_records),
            "candidateEvaluation": evaluation["summary"],
            "deduplicatedReports": sum(row.get("reportCount", 0) for row in event_candidates),
            "uniqueEvents": len(event_candidates),
            "eventDuplicateReports": sum(max(0, row.get("reportCount", 0) - 1) for row in event_candidates),
            "domestic": stats(domestic),
            "international": stats(international),
        },
    }


def run(required_date: date, *, window_days: int = 7, query_results: list[dict] | None = None, query_audits: list[dict] | None = None, execute_query_search: bool = True, perform_evidence_upgrade: bool = True, write: bool = False, output_path: Path | None = None) -> dict:
    start = required_date - timedelta(days=window_days - 1)
    statuses, raw = [], []
    for spec in SOURCE_SCANS:
        status, rows = scan_page(spec, start, required_date)
        statuses.append(status)
        raw.extend(rows)
    if execute_query_search and query_audits is None:
        searched, audits = execute_queries(required_date, start, required_date)
        query_results = (query_results or []) + searched
        query_audits = audits
    audit = build_audit(required_date, raw, statuses, query_results or [], query_audits or [], perform_evidence_upgrade=perform_evidence_upgrade)
    if write:
        DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
        (DISCOVERY_DIR / "README.md").write_text(
            "# 日报 broad discovery 审计\n\n此目录只记录日报发现层，不进入 `content/监测/`，也不改变行业关注地图固定六源。未知公众号可以作为 discovery source，但不能直接作为最终 evidence。\n",
            encoding="utf-8",
        )
        target = output_path or (DISCOVERY_DIR / f"{required_date.isoformat()}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return audit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run auditable daily broad discovery source scans.")
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--query-results", type=Path, help="JSON list of Codex-executed search results")
    parser.add_argument("--no-query-search", action="store_true", help="Skip real RSS query execution (tests/replay only)")
    parser.add_argument("--no-evidence-upgrade", action="store_true", help="Skip evidence upgrade (tests/replay only)")
    parser.add_argument("--output", type=Path, help="Optional audit output path; defaults to content/发现/YYYY-MM-DD.json")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.window_days < 1:
        parser.error("--window-days must be positive")
    query_results = load_json(args.query_results, []) if args.query_results else []
    if not isinstance(query_results, list):
        parser.error("--query-results must contain a JSON list")
    audit = run(args.date, window_days=args.window_days, query_results=query_results, execute_query_search=not args.no_query_search, perform_evidence_upgrade=not args.no_evidence_upgrade, write=args.write, output_path=args.output)
    print(json.dumps(audit["summary"], ensure_ascii=False, indent=2))
    for status in audit["sourceScans"]:
        print(f'{status["sourceId"]}: {status["status"]} raw={status["rawResults"]} window={status["windowResults"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
